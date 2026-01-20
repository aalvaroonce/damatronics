"""
robot_driver.py
===============

VERSIÓN ANTI-TUNNELING – CONTROLADOR DE ROBOT DE DAMAS
-----------------------------------------------------

Controlador individual para cada robot-ficha del tablero de damas.

Objetivo principal:
- Ejecutar movimientos enviados por el Supervisor de forma estable y precisa.
- Evitar el problema de "tunneling" (saltarse la condición de llegada por exceso
  de velocidad), que provocaba giros infinitos o no detección de destino.

Solución implementada:
- Curva de frenado progresiva al aproximarse al destino.
- Zona amplia de tolerancia de llegada (6 cm).
- Velocidad de aproximación muy baja en los últimos centímetros.
- Ignorar correcciones angulares cuando el robot está muy cerca del objetivo.

Diseño orientado a Clean Code:
- Máquina de estados explícita (IDLE, ROTATING, MOVING).
- Separación clara entre percepción, control y actuación.
- Parámetros de control centralizados y documentados.
- Métodos pequeños con responsabilidad única.
"""

from controller import Robot
import math


class CheckerRobotDriver:
    """
    Controlador de bajo nivel para una ficha (robot) del juego de damas.

    Esta clase se encarga de:
    - Recibir órdenes del Supervisor.
    - Rotar el robot hacia su destino.
    - Avanzar manteniendo rumbo.
    - Frenar progresivamente para evitar overshooting.
    - Notificar al Supervisor cuando el destino ha sido alcanzado.
    """

    def __init__(self):
        """
        Inicializa el robot, sensores, actuadores y variables de control.
        """
        # Robot base
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())
        self.name = self.robot.getName()

        # Motores de tracción diferencial
        self.left_motor = self.robot.getDevice('left_motor')
        self.right_motor = self.robot.getDevice('right_motor')

        # Configuración de motores en modo velocidad
        self.left_motor.setPosition(float('inf'))
        self.right_motor.setPosition(float('inf'))
        self.left_motor.setVelocity(0.0)
        self.right_motor.setVelocity(0.0)

        # Sensores de posicionamiento
        self.gps = self.robot.getDevice('gps')
        self.gps.enable(self.timestep)

        self.compass = self.robot.getDevice('compass')
        self.compass.enable(self.timestep)

        # Comunicación con el Supervisor
        self.receiver = self.robot.getDevice('receiver')
        self.receiver.enable(self.timestep)
        self.emitter = self.robot.getDevice('emitter')

        # Conector superior (usado para la corona)
        self.connector = self.robot.getDevice('upper_connector')

        # ---------------- ESTADO INTERNO ----------------
        self.state = "IDLE"     # IDLE | ROTATING | MOVING
        self.target_x = 0.0     # Destino en coordenadas del mundo
        self.target_y = 0.0

        # ---------------- CONFIGURACIÓN DE SEGURIDAD ----------------
        # Zona amplia de llegada para evitar tunneling
        self.TOLERANCE_DIST = 0.06   # 6 cm
        self.TOLERANCE_ANGLE = 0.04  # Radianes (~2.3º)

        # Offset del compás (ajuste de orientación del modelo)
        self.COMPASS_OFFSET = math.pi / 2

        # ---------------- PARÁMETROS DE CONTROL ----------------
        self.KP_ROT = 1.5             # Ganancia proporcional de rotación
        self.KP_MOVE = 3.0            # Ganancia de corrección en avance
        self.MAX_SPEED_CRUISE = 6.0   # Velocidad máxima en trayecto largo
        self.APPROACH_SPEED = 0.5     # Velocidad mínima de aproximación

    def get_bearing(self):
        """
        Obtiene la orientación actual del robot en radianes.

        :return: Ángulo absoluto del robot en el plano.
        """
        north = self.compass.getValues()
        rad = math.atan2(north[1], north[0])
        return -rad + self.COMPASS_OFFSET

    def get_angle_to_target(self):
        """
        Calcula el ángulo desde la posición actual hasta el destino.

        :return: Ángulo objetivo en radianes.
        """
        pos = self.gps.getValues()
        dx = self.target_x - pos[0]
        dy = self.target_y - pos[1]
        return math.atan2(dy, dx)

    def normalize_angle(self, angle):
        """
        Normaliza un ángulo al rango [-pi, pi].

        :param angle: Ángulo en radianes.
        :return: Ángulo normalizado.
        """
        while angle > math.pi:
            angle -= 2 * math.pi
        while angle < -math.pi:
            angle += 2 * math.pi
        return angle

    def clamp(self, value, min_val, max_val):
        """
        Limita un valor dentro de un rango, preservando el signo.

        Incluye una zona muerta para evitar micro-oscilaciones.

        :param value: Valor a limitar.
        :param min_val: Magnitud mínima.
        :param max_val: Magnitud máxima.
        :return: Valor limitado.
        """
        if abs(value) < 0.01:
            return 0.0

        sign = 1 if value > 0 else -1
        mag = abs(value)

        if mag > max_val:
            mag = max_val
        if mag < min_val:
            mag = min_val

        return mag * sign

    def process_messages(self):
        """
        Procesa los mensajes entrantes desde el Supervisor.

        Comandos soportados:
        - MOVE x y : mover el robot a una posición.
        - DIE x y  : (tratado igual que MOVE, mantenido por compatibilidad).
        - LOCK    : bloquear el conector superior.
        """
        while self.receiver.getQueueLength() > 0:
            msg = self.receiver.getString()
            self.receiver.nextPacket()

            # Ignorar mensajes que no son para este robot
            if not msg.startswith(self.name):
                continue

            parts = msg.split()
            cmd = parts[1]

            if cmd == "MOVE" or cmd == "DIE":
                self.target_x = float(parts[2])
                self.target_y = float(parts[3])
                self.state = "ROTATING"
                print(f"🤖 {self.name} -> Moviendo a ({self.target_x:.2f}, {self.target_y:.2f})")

            elif cmd == "LOCK":
                if self.connector:
                    self.connector.lock()

    def run(self):
        """
        Bucle principal del controlador del robot.

        Implementa una máquina de estados:
        - IDLE: robot detenido.
        - ROTATING: alineación angular con el objetivo.
        - MOVING: avance con corrección y frenado progresivo.
        """
        while self.robot.step(self.timestep) != -1:
            self.process_messages()

            # ---------------- ESTADO: IDLE ----------------
            if self.state == "IDLE":
                self.left_motor.setVelocity(0)
                self.right_motor.setVelocity(0)

            # ---------------- ESTADO: ROTATING ----------------
            elif self.state == "ROTATING":
                current_angle = self.get_bearing()
                target_angle = self.get_angle_to_target()
                error_angle = self.normalize_angle(target_angle - current_angle)

                # Si el error angular es pequeño, pasamos a avanzar
                if abs(error_angle) < self.TOLERANCE_ANGLE:
                    self.left_motor.setVelocity(0)
                    self.right_motor.setVelocity(0)
                    self.state = "MOVING"
                    continue

                rot_speed = error_angle * self.KP_ROT
                rot_speed = self.clamp(rot_speed, 0.1, 2.0)

                self.left_motor.setVelocity(-rot_speed)
                self.right_motor.setVelocity(rot_speed)

            # ---------------- ESTADO: MOVING ----------------
            elif self.state == "MOVING":
                pos = self.gps.getValues()
                dx = self.target_x - pos[0]
                dy = self.target_y - pos[1]
                dist = math.sqrt(dx * dx + dy * dy)

                # 1. CHEQUEO DE LLEGADA (ANTI-TUNNELING)
                if dist < self.TOLERANCE_DIST:
                    self.left_motor.setVelocity(0)
                    self.right_motor.setVelocity(0)
                    self.state = "IDLE"
                    self.emitter.send(f"{self.name} ARRIVED".encode('utf-8'))
                    print(f"✅ {self.name} Llegó. Stop & Snap.")
                    continue

                # 2. MANTENIMIENTO DE RUMBO
                # Cerca del objetivo se ignora el error angular para evitar giros
                error_angle = 0
                if dist >= 0.20:
                    current_angle = self.get_bearing()
                    target_angle = self.get_angle_to_target()
                    error_angle = self.normalize_angle(target_angle - current_angle)

                correction = error_angle * self.KP_MOVE

                # 3. GESTIÓN DE VELOCIDAD (CURVA DE FRENADO)
                if dist > 0.40:
                    base_speed = self.MAX_SPEED_CRUISE
                else:
                    # Frenado progresivo para evitar overshooting
                    base_speed = max(self.APPROACH_SPEED, dist * 5.0)
                    base_speed = min(base_speed, 2.0)

                self.left_motor.setVelocity(base_speed - correction)
                self.right_motor.setVelocity(base_speed + correction)


def main():
    """
    Punto de entrada del controlador del robot.
    """
    driver = CheckerRobotDriver()
    driver.run()


if __name__ == "__main__":
    main()
