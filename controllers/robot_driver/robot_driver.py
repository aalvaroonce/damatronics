"""
robot_driver.py
Piloto Automático: Navegación autónoma de cada ficha
"""

from controller import Robot
import math
import struct

class CheckerRobotDriver:
    def __init__(self):
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())
        self.name = self.robot.getName()
        
        # Motores
        self.left_motor = self.robot.getDevice('left_motor')
        self.right_motor = self.robot.getDevice('right_motor')
        
        # Configurar motores en modo velocidad
        self.left_motor.setPosition(float('inf'))
        self.right_motor.setPosition(float('inf'))
        self.left_motor.setVelocity(0.0)
        self.right_motor.setVelocity(0.0)
        
        # Sensores
        self.gps = self.robot.getDevice('gps')
        self.gps.enable(self.timestep)
        
        self.compass = self.robot.getDevice('compass')
        self.compass.enable(self.timestep)
        
        self.receiver = self.robot.getDevice('receiver')
        self.receiver.enable(self.timestep)
        
        # Conector para corona
        self.connector = self.robot.getDevice('upper_connector')
        
        # Estado del robot
        self.state = "IDLE"  # IDLE, ROTATING, MOVING, LOCKING
        self.target_x = None
        self.target_y = None
        self.target_angle = None
        
        # Parámetros de control
        self.max_speed = 2.0
        self.rotation_speed = 1.5
        self.angle_tolerance = 0.05  # radianes (~3 grados)
        self.distance_tolerance = 0.01  # metros (1cm)
        
        print(f"🤖 Robot {self.name} inicializado")
    
    def get_position(self):
        """Obtiene posición actual del GPS"""
        values = self.gps.getValues()
        return values[0], values[1]  # x, y
    
    def get_bearing(self):
        """Obtiene orientación actual del Compass"""
        north = self.compass.getValues()
        # Ángulo respecto al norte (eje Y positivo)
        angle = math.atan2(north[0], north[1])
        return angle
    
    def calculate_angle_to_target(self):
        """Calcula ángulo necesario para mirar al objetivo"""
        current_x, current_y = self.get_position()
        dx = self.target_x - current_x
        dy = self.target_y - current_y
        return math.atan2(dx, dy)
    
    def calculate_distance_to_target(self):
        """Calcula distancia al objetivo"""
        current_x, current_y = self.get_position()
        dx = self.target_x - current_x
        dy = self.target_y - current_y
        return math.sqrt(dx*dx + dy*dy)
    
    def normalize_angle(self, angle):
        """Normaliza ángulo al rango [-π, π]"""
        while angle > math.pi:
            angle -= 2 * math.pi
        while angle < -math.pi:
            angle += 2 * math.pi
        return angle
    
    def process_message(self):
        """Procesa mensajes del Supervisor"""

        if self.receiver.getQueueLength() > 0:
            message = self.receiver.getString() 
            self.receiver.nextPacket()
            
            # Filtrar: solo procesar si el mensaje es para este robot
            if not message.startswith(self.name):
                return
            
            parts = message.split()
            command = parts[1]
            
            print(f"📨 {self.name} recibió: {message}")
            
            if command == "MOVE":
                self.target_x = float(parts[2])
                self.target_y = float(parts[3])
                self.state = "ROTATING"
                print(f"🎯 Objetivo: ({self.target_x:.3f}, {self.target_y:.3f})")
            
            elif command == "DIE":
                self.target_x = float(parts[2])
                self.target_y = float(parts[3])
                self.state = "ROTATING"
                print(f"💀 {self.name} va al cementerio...")
            
            elif command == "LOCK":
                self.state = "LOCKING"
                print(f"👑 {self.name} activando corona...")
    
    def rotate_to_target(self):
        """Fase 1: Rotar hacia el objetivo"""
        current_angle = self.get_bearing()
        self.target_angle = self.calculate_angle_to_target()
        
        angle_diff = self.normalize_angle(self.target_angle - current_angle)
        
        # Si ya está orientado, pasar a movimiento
        if abs(angle_diff) < self.angle_tolerance:
            self.left_motor.setVelocity(0)
            self.right_motor.setVelocity(0)
            self.state = "MOVING"
            print(f"✅ Rotación completa, avanzando...")
            return
        
        # Rotar en el sentido correcto
        if angle_diff > 0:
            # Girar a la izquierda
            self.left_motor.setVelocity(-self.rotation_speed)
            self.right_motor.setVelocity(self.rotation_speed)
        else:
            # Girar a la derecha
            self.left_motor.setVelocity(self.rotation_speed)
            self.right_motor.setVelocity(-self.rotation_speed)
    
    def move_forward(self):
        """Fase 2: Avanzar hacia el objetivo"""
        distance = self.calculate_distance_to_target()
        
        # Si llegó al destino, detenerse
        if distance < self.distance_tolerance:
            self.left_motor.setVelocity(0)
            self.right_motor.setVelocity(0)
            self.state = "IDLE"
            print(f"✅ {self.name} llegó al destino")
            return
        
        # Corrección de trayectoria simple
        current_angle = self.get_bearing()
        target_angle = self.calculate_angle_to_target()
        angle_error = self.normalize_angle(target_angle - current_angle)
        
        # Control proporcional simple
        base_speed = min(self.max_speed, distance * 5)  # Frenar cerca del objetivo
        correction = angle_error * 0.5
        
        left_speed = base_speed - correction
        right_speed = base_speed + correction
        
        # Limitar velocidades
        left_speed = max(-self.max_speed, min(self.max_speed, left_speed))
        right_speed = max(-self.max_speed, min(self.max_speed, right_speed))
        
        self.left_motor.setVelocity(left_speed)
        self.right_motor.setVelocity(right_speed)
    
    def lock_crown(self):
        """Fase 3: Activar conector magnético"""
        if self.connector:
            self.connector.lock()
            print(f"🔒 {self.name} conectó la corona")
        self.state = "IDLE"
    
    def run(self):
        """Loop principal del robot"""
        while self.robot.step(self.timestep) != -1:
            # Procesar mensajes entrantes
            self.process_message()
            
            # Máquina de estados
            if self.state == "ROTATING":
                self.rotate_to_target()
            
            elif self.state == "MOVING":
                self.move_forward()
            
            elif self.state == "LOCKING":
                self.lock_crown()
            
            # IDLE: Esperar sin hacer nada

def main():
    driver = CheckerRobotDriver()
    driver.run()

if __name__ == "__main__":
    main()