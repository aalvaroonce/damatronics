"""
robot_driver.py - VERSIÓN ANTI-TUNNELING
Solución al problema del giro infinito:
El robot ahora frena obligatoriamente antes de llegar para asegurar
que la comprobación de distancia (if dist < tolerance) no se salte
por ir demasiado rápido (efecto tunneling).
"""

from controller import Robot
import math

class CheckerRobotDriver:
    def __init__(self):
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())
        self.name = self.robot.getName()
        
        self.left_motor = self.robot.getDevice('left_motor')
        self.right_motor = self.robot.getDevice('right_motor')
        
        self.left_motor.setPosition(float('inf'))
        self.right_motor.setPosition(float('inf'))
        self.left_motor.setVelocity(0.0)
        self.right_motor.setVelocity(0.0)
        
        self.gps = self.robot.getDevice('gps')
        self.gps.enable(self.timestep)
        
        self.compass = self.robot.getDevice('compass')
        self.compass.enable(self.timestep)
        
        self.receiver = self.robot.getDevice('receiver')
        self.receiver.enable(self.timestep)
        self.emitter = self.robot.getDevice('emitter')
        
        self.connector = self.robot.getDevice('upper_connector')
        
        # --- ESTADO ---
        self.state = "IDLE"
        self.target_x = 0.0
        self.target_y = 0.0
        
        # --- CONFIGURACIÓN DE SEGURIDAD ---
        self.TOLERANCE_DIST = 0.06 # 6cm (Zona amplia de llegada)
        self.TOLERANCE_ANGLE = 0.04
        
        # Mantenemos tu offset de 90 grados
        self.COMPASS_OFFSET = math.pi / 2 
        
        # Parámetros de control
        self.KP_ROT = 1.5         
        self.KP_MOVE = 3.0        
        self.MAX_SPEED_CRUISE = 6.0  # Velocidad máxima en trayecto largo
        self.APPROACH_SPEED = 0.5    # Velocidad de llegada (MUY LENTA)

    def get_bearing(self):
        north = self.compass.getValues()
        rad = math.atan2(north[1], north[0])
        return -rad + self.COMPASS_OFFSET

    def get_angle_to_target(self):
        pos = self.gps.getValues()
        dx = self.target_x - pos[0]
        dy = self.target_y - pos[1]
        return math.atan2(dy, dx)

    def normalize_angle(self, angle):
        while angle > math.pi: angle -= 2*math.pi
        while angle < -math.pi: angle += 2*math.pi
        return angle

    def clamp(self, value, min_val, max_val):
        if abs(value) < 0.01: return 0.0
        sign = 1 if value > 0 else -1
        mag = abs(value)
        if mag > max_val: mag = max_val
        if mag < min_val: mag = min_val 
        return mag * sign

    def process_messages(self):
        while self.receiver.getQueueLength() > 0:
            msg = self.receiver.getString()
            self.receiver.nextPacket()
            if not msg.startswith(self.name): continue
            parts = msg.split()
            cmd = parts[1]
            if cmd == "MOVE" or cmd == "DIE":
                self.target_x = float(parts[2])
                self.target_y = float(parts[3])
                self.state = "ROTATING"
                print(f"🤖 {self.name} -> Moviendo a ({self.target_x:.2f}, {self.target_y:.2f})")
            elif cmd == "LOCK":
                if self.connector: self.connector.lock()
                
    def run(self):
        while self.robot.step(self.timestep) != -1:
            self.process_messages()
            
            if self.state == "IDLE":
                self.left_motor.setVelocity(0)
                self.right_motor.setVelocity(0)
                
            elif self.state == "ROTATING":
                current_angle = self.get_bearing()
                target_angle = self.get_angle_to_target()
                error_angle = self.normalize_angle(target_angle - current_angle)
                
                if abs(error_angle) < self.TOLERANCE_ANGLE:
                    self.left_motor.setVelocity(0)
                    self.right_motor.setVelocity(0)
                    self.state = "MOVING"
                    continue

                rot_speed = error_angle * self.KP_ROT
                rot_speed = self.clamp(rot_speed, 0.1, 2.0)
                
                self.left_motor.setVelocity(-rot_speed)  
                self.right_motor.setVelocity(rot_speed) 
            
            elif self.state == "MOVING":
                pos = self.gps.getValues()
                dx = self.target_x - pos[0]
                dy = self.target_y - pos[1]
                dist = math.sqrt(dx*dx + dy*dy)
                
                # 1. CHEQUEO DE LLEGADA (Zona de 6cm)
                if dist < self.TOLERANCE_DIST:
                    self.left_motor.setVelocity(0)
                    self.right_motor.setVelocity(0)
                    self.state = "IDLE"
                    self.emitter.send(f"{self.name} ARRIVED".encode('utf-8'))
                    print(f"✅ {self.name} Llegó. Stop & Snap.")
                    continue

                # 2. MANTENIMIENTO DE RUMBO
                # Si estamos cerca (<20cm), ignoramos errores de ángulo para no girar
                error_angle = 0
                if dist >= 0.20:
                    current_angle = self.get_bearing()
                    target_angle = self.get_angle_to_target()
                    error_angle = self.normalize_angle(target_angle - current_angle)
                
                correction = error_angle * self.KP_MOVE
                
                # 3. GESTIÓN DE VELOCIDAD (CURVA DE FRENADO)
                # Si estamos lejos (> 40cm), vamos rápido.
                # Si estamos cerca, reducimos velocidad proporcionalmente.
                if dist > 0.40:
                    base_speed = self.MAX_SPEED_CRUISE
                else:
                    # Entre 0cm y 40cm, la velocidad baja de 2.0 a 0.5
                    # Esto fuerza al robot a "gatear" los últimos centímetros.
                    base_speed = max(self.APPROACH_SPEED, dist * 5.0)
                    # Limitamos por arriba para que la transición no sea brusca
                    base_speed = min(base_speed, 2.0)
                
                self.left_motor.setVelocity(base_speed - correction)
                self.right_motor.setVelocity(base_speed + correction)

def main():
    driver = CheckerRobotDriver()
    driver.run()

if __name__ == "__main__":
    main()