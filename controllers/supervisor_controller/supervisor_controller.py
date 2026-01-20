"""
supervisor_controller.py
========================

--- DAMAS ---
--------------------------------

Controlador Supervisor para un juego de damas implementado en Webots.

Este módulo es responsable de:
- Gestionar la lógica completa del juego (turnos, movimientos, capturas y combos).
- Mantener el estado del tablero y de cada ficha (robot).
- Validar reglas de movimiento para fichas normales y damas (reyes).
- Coordinar la comunicación con los robots mediante Emitter/Receiver.
- Gestionar la coronación (promoción a dama) mediante la generación dinámica
  de una corona física perfectamente alineada.
- Garantizar un "snap" preciso entre robot y corona tras cada movimiento.

Mejoras clave implementadas:
1. La corona se genera plana (rotación corregida para eje Z).
2. El conector de la corona está orientado hacia abajo para un acople fiable.
3. Snap sincronizado: al mover la ficha, la corona se reposiciona junto a ella.

Diseño orientado a Clean Code:
- Separación clara de responsabilidades por método.
- Nombres descriptivos y coherentes.
- Métodos pequeños y especializados.
- Comentarios explicativos solo donde aportan contexto no evidente.
"""

from controller import Supervisor
import math


class CheckersGame:
    """
    Clase principal que encapsula toda la lógica del juego de damas.

    Esta clase actúa como:
    - Controlador del estado del juego.
    - Orquestador de la interacción usuario ↔ tablero ↔ robots.
    - Supervisor de reglas, turnos y eventos especiales (capturas, coronación).

    El ciclo de vida del juego se gestiona mediante el método `run()`.
    """

    def __init__(self):
        """
        Inicializa el supervisor, dispositivos de comunicación y estado inicial
        del juego.
        """
        # Supervisor de Webots
        self.supervisor = Supervisor()
        self.timestep = int(self.supervisor.getBasicTimeStep())

        # Dispositivos de comunicación con los robots
        self.emitter = self.supervisor.getDevice('emitter')
        self.receiver = self.supervisor.getDevice('receiver')
        self.receiver.enable(self.timestep)

        # Estado del tablero (8x8). Cada celda contiene el nombre del robot o None.
        self.board = [[None for _ in range(8)] for _ in range(8)]

        # Equipo al que le corresponde el turno actual
        self.current_team = "WHITE"

        # Estado de selección del usuario
        self.selected_piece = None       # Nombre del robot seleccionado
        self.selected_grid = None        # Coordenadas (x, y) en el tablero

        # Estado de movimiento asíncrono
        self.waiting_for_robot = False
        self.moving_robot_name = None
        self.moving_robot_target = None

        # Ficha forzada a continuar una captura múltiple (combo)
        self.forced_piece = None

        # Diccionario de robots indexados por nombre
        self.robots = {}
        self.init_robots()
        self.init_board()

        print("=== DAMAS : LAS DAMAS DE TODA LA VIDA ===")

    def init_robots(self):
        """
        Inicializa la información de todos los robots del tablero.

        Se detectan los robots definidos en el mundo (DEF) y se almacena:
        - Nodo del robot.
        - Equipo (WHITE / BLACK).
        - Estado de dama (is_king).
        - Estado de vida (alive).
        - Referencias a los campos de transformación.
        """
        white_names = [f"W_{i:02d}" for i in range(1, 13)]
        black_names = [f"B_{i:02d}" for i in range(1, 13)]

        for name in white_names + black_names:
            robot_node = self.supervisor.getFromDef(name)
            if robot_node:
                self.robots[name] = {
                    'node': robot_node,
                    'team': 'WHITE' if name.startswith('W') else 'BLACK',
                    'is_king': False,
                    'alive': True,
                    'trans_field': robot_node.getField("translation"),
                    'rot_field': robot_node.getField("rotation")
                }

    def init_board(self):
        """
        Inicializa el tablero lógico a partir de la posición física
        de los robots en el mundo.
        """
        for name, robot_info in self.robots.items():
            if robot_info['alive']:
                pos = robot_info['trans_field'].getSFVec3f()
                x, y = self.world_to_grid(pos[0], pos[1])
                if 0 <= x < 8 and 0 <= y < 8:
                    self.board[y][x] = name
        self.print_board()

    def world_to_grid(self, world_x, world_y):
        """
        Convierte coordenadas del mundo Webots a coordenadas del tablero.

        :param world_x: Posición X en el mundo.
        :param world_y: Posición Y en el mundo.
        :return: Tupla (grid_x, grid_y).
        """
        grid_x = int(round((world_x + 0.7) / 0.2))
        grid_y = int(round((world_y + 0.7) / 0.2))
        return grid_x, grid_y

    def grid_to_world(self, grid_x, grid_y):
        """
        Convierte coordenadas del tablero a coordenadas del mundo Webots.

        :param grid_x: Columna del tablero.
        :param grid_y: Fila del tablero.
        :return: Tupla (world_x, world_y).
        """
        world_x = -0.7 + grid_x * 0.2
        world_y = -0.7 + grid_y * 0.2
        return world_x, world_y

    def print_board(self):
        """
        Imprime una representación textual del tablero en consola.

        Incluye:
        - Identificador de ficha.
        - Indicador de dama (*).
        - Indicador de selección ([ ]).
        """
        print("\n=== TABLERO ===")
        for y in range(7, -1, -1):
            row = []
            for x in range(8):
                piece = self.board[y][x]
                if piece:
                    team_char = piece[0]
                    symbol = team_char + piece[-2:]
                    if self.robots[piece]['is_king']:
                        symbol = f"*{symbol}*"
                    if piece == self.selected_piece:
                        symbol = f"[{symbol}]"
                    row.append(f"{symbol:^6}")
                else:
                    row.append("  .   ")
            print(f"{y}: " + " ".join(row))
        print("   " + " ".join([f"  {i}   " for i in range(8)]))

    def check_user_selection(self):
        """
        Detecta cambios en la selección del usuario en el entorno Webots
        y redirige el evento al manejador correspondiente.
        """
        selected_node = self.supervisor.getSelected()
        if selected_node is None:
            return

        node_name = selected_node.getDef()
        if not node_name:
            return

        if node_name in self.robots:
            self.handle_robot_click(node_name)
        elif node_name.startswith("TILE_"):
            parts = node_name.split("_")
            if len(parts) == 3:
                self.handle_tile_click(int(parts[1]), int(parts[2]))

    def handle_robot_click(self, robot_name):
        """
        Gestiona la selección de una ficha (robot) por parte del usuario.
        """
        if self.waiting_for_robot:
            return

        if self.forced_piece and robot_name != self.forced_piece:
            print(f"⚠️ ¡COMBO OBLIGATORIO! Debes seguir usando {self.forced_piece}")
            return

        robot_info = self.robots[robot_name]
        if robot_info['team'] != self.current_team:
            print(f"❌ Turno de {self.current_team}")
            return
        if not robot_info['alive']:
            return

        self.selected_piece = robot_name
        for y in range(8):
            for x in range(8):
                if self.board[y][x] == robot_name:
                    self.selected_grid = (x, y)
                    break
        print(f"✅ Seleccionado: {robot_name}")

    def handle_tile_click(self, x, y):
        """
        Gestiona el intento de movimiento hacia una casilla del tablero.
        """
        if self.waiting_for_robot or self.selected_piece is None:
            return

        valid, captured_piece = self.validate_move(self.selected_grid, (x, y))

        if valid:
            self.execute_move(self.selected_grid, (x, y), captured_piece)
        else:
            print("❌ Movimiento inválido")
            if not self.forced_piece:
                self.selected_piece = None

    def validate_move(self, origin, destination):
        """
        Valida un movimiento según las reglas de las damas.

        Soporta:
        - Movimiento normal.
        - Captura simple.
        - Captura múltiple obligatoria.
        - Movimiento y captura de damas voladoras.

        :return: (is_valid, captured_piece_name or None)
        """
        ox, oy = origin
        dx, dy = destination

        if self.board[dy][dx] is not None:
            return False, None

        piece_name = self.board[oy][ox]
        info = self.robots[piece_name]
        team = info['team']
        is_king = info['is_king']

        diff_x = dx - ox
        diff_y = dy - oy

        if abs(diff_x) != abs(diff_y):
            return False, None

        direction_x = 1 if diff_x > 0 else -1
        direction_y = 1 if diff_y > 0 else -1

        # Lógica para fichas normales
        if not is_king:
            if abs(diff_x) == 1:
                if self.forced_piece:
                    return False, None
                if team == "WHITE" and diff_y < 0:
                    return False, None
                if team == "BLACK" and diff_y > 0:
                    return False, None
                return True, None

            if abs(diff_x) == 2:
                mid_x = ox + direction_x
                mid_y = oy + direction_y
                victim = self.board[mid_y][mid_x]
                if victim and self.robots[victim]['team'] != team:
                    return True, victim
            return False, None

        # Lógica para damas voladoras
        steps = abs(diff_x)
        victim = None
        for i in range(1, steps):
            check_x = ox + (i * direction_x)
            check_y = oy + (i * direction_y)
            found_piece = self.board[check_y][check_x]

            if found_piece:
                if victim is None:
                    if self.robots[found_piece]['team'] != team:
                        victim = found_piece
                    else:
                        return False, None
                else:
                    return False, None

        if victim:
            return True, victim
        else:
            if self.forced_piece:
                return False, None
            return True, None

    def can_capture_more(self, piece_name, current_x, current_y):
        """
        Determina si una ficha puede continuar capturando tras una captura previa.
        """
        info = self.robots[piece_name]
        is_king = info['is_king']
        directions = [(-1, -1), (-1, 1), (1, -1), (1, 1)]

        if not is_king:
            for dx, dy in directions:
                dest_x, dest_y = current_x + dx * 2, current_y + dy * 2
                if 0 <= dest_x < 8 and 0 <= dest_y < 8:
                    valid, _ = self.validate_move(
                        (current_x, current_y),
                        (dest_x, dest_y)
                    )
                    if valid:
                        return True
        else:
            for dx, dy in directions:
                for dist in range(2, 8):
                    dest_x, dest_y = current_x + dx * dist, current_y + dy * dist
                    if 0 <= dest_x < 8 and 0 <= dest_y < 8:
                        valid, victim = self.validate_move(
                            (current_x, current_y),
                            (dest_x, dest_y)
                        )
                        if valid and victim:
                            return True
                    else:
                        break
        return False

    def execute_move(self, origin, destination, captured_piece):
        """
        Ejecuta un movimiento válido:
        - Actualiza el tablero lógico.
        - Elimina piezas capturadas.
        - Envía el comando de movimiento al robot.
        - Gestiona promociones y combos.
        """
        ox, oy = origin
        dx, dy = destination
        piece = self.board[oy][ox]
        robot_info = self.robots[piece]

        if captured_piece:
            self.capture_piece(captured_piece)

        self.board[dy][dx] = piece
        self.board[oy][ox] = None

        wx, wy = self.grid_to_world(dx, dy)
        msg = f"{piece} MOVE {wx:.4f} {wy:.4f}"
        self.emitter.send(msg.encode('utf-8'))

        self.waiting_for_robot = True
        self.moving_robot_name = piece
        self.moving_robot_target = (dx, dy)

        will_promote = False
        if not robot_info['is_king']:
            if (robot_info['team'] == "WHITE" and dy == 7) or \
               (robot_info['team'] == "BLACK" and dy == 0):
                will_promote = True

        if captured_piece and not will_promote and \
           self.can_capture_more(piece, dx, dy):
            self.forced_piece = piece
            print(f"🔥 ¡COMBO! {piece} puede seguir comiendo. Turno mantenido.")
        else:
            self.forced_piece = None

        self.selected_piece = None
        self.print_board()

    def promote_king(self, piece_name):
        """
        Promociona una ficha a dama (rey).

        Se genera dinámicamente una corona:
        - Cilindro plano (orientado al eje Z).
        - Conector orientado hacia abajo.
        - Altura calculada para un acople perfecto.
        """
        self.robots[piece_name]['is_king'] = True

        pos = self.robots[piece_name]['trans_field'].getSFVec3f()
        wx, wy = pos[0], pos[1]

        # Altura exacta: robot (0.05) + conector (0.085)
        spawn_z = 0.135

        print(f"👑 INVOCANDO CORONA para {piece_name}...")

        root_children = self.supervisor.getRoot().getField("children")
        crown_def = f"CROWN_{piece_name}"

        crown_vrml = f"""
        DEF {crown_def} Solid {{
          translation {wx} {wy} {spawn_z}
          rotation 0 0 1 1.5708
          children [
            Shape {{
              appearance PBRAppearance {{
                baseColor 1 0.84 0
                metalness 0.8
                roughness 0.2
              }}
              geometry Cylinder {{
                height 0.02
                radius 0.06
              }}
            }}
            Connector {{
              name "crown_connector"
              type "symmetric"
              autoLock TRUE
              distanceTolerance 0.05
              axisTolerance 0.5
              rotation 0 0 1 -1.5708
            }}
          ]
          boundingObject Cylinder {{ height 0.02 radius 0.06 }}
          physics Physics {{ mass 0.01 density -1 }}
        }}
        """
        root_children.importMFNodeFromString(-1, crown_vrml)

        # Forzar el acople inmediato
        self.emitter.send(f"{piece_name} LOCK".encode('utf-8'))

    def capture_piece(self, piece_name):
        """
        Elimina una ficha del juego aplicando una animación física
        y actualizando el estado lógico.
        """
        robot = self.robots[piece_name]
        node = robot['node']
        team = robot['team']
        jump_dir = 1.0 if team == "WHITE" else -1.0

        node.setVelocity([
            jump_dir * 40.0, 0.0, 50.0,
            0.0, 50.0, 0.0
        ])

        robot['alive'] = False

        for y in range(8):
            for x in range(8):
                if self.board[y][x] == piece_name:
                    self.board[y][x] = None

        print(f"🚀☄️ ¡YEET! {piece_name} eliminada.")

    def snap_robot_to_grid(self, robot_name, grid_x, grid_y):
        """
        Realiza un 'snap' preciso del robot y su corona (si existe)
        a la celda del tablero correspondiente.
        """
        robot = self.robots[robot_name]
        node = robot['node']
        target_wx, target_wy = self.grid_to_world(grid_x, grid_y)

        # Snap del robot
        node.resetPhysics()
        robot['trans_field'].setSFVec3f([target_wx, target_wy, 0.05])
        robot['rot_field'].setSFRotation([0, 0, 1, 0])

        # Snap de la corona si es dama
        if robot['is_king']:
            crown_node = self.supervisor.getFromDef(f"CROWN_{robot_name}")
            if crown_node:
                crown_node.resetPhysics()
                crown_node.getField("translation").setSFVec3f(
                    [target_wx, target_wy, 0.135]
                )
                crown_node.getField("rotation").setSFRotation(
                    [0, 0, 1, 1.5708]
                )

        print(f"✨ SNAP: {robot_name} fijado.")

    def process_robot_messages(self):
        """
        Procesa los mensajes entrantes de los robots.

        Se utiliza principalmente para detectar la finalización
        de un movimiento (ARRIVED).
        """
        while self.receiver.getQueueLength() > 0:
            msg = self.receiver.getString()
            self.receiver.nextPacket()

            parts = msg.split()
            sender = parts[0]
            command = parts[1]

            if command == "ARRIVED" and sender == self.moving_robot_name:
                tx, ty = self.moving_robot_target

                self.snap_robot_to_grid(sender, tx, ty)

                robot_info = self.robots[sender]
                if not robot_info['is_king']:
                    if (robot_info['team'] == "WHITE" and ty == 7) or \
                       (robot_info['team'] == "BLACK" and ty == 0):
                        self.promote_king(sender)

                if self.forced_piece:
                    self.waiting_for_robot = False
                    self.selected_piece = self.forced_piece
                    print(f"⚔️ ¡Sigue saltando con {self.forced_piece}!")
                else:
                    self.moving_robot_name = None
                    self.moving_robot_target = None
                    self.waiting_for_robot = False
                    self.switch_turn()

    def switch_turn(self):
        """
        Alterna el turno entre los equipos WHITE y BLACK.
        """
        self.current_team = "BLACK" if self.current_team == "WHITE" else "WHITE"
        print(f"\n🔄 Turno: {self.current_team}")

    def run(self):
        """
        Bucle principal del juego.

        Controla:
        - Selección del usuario.
        - Procesamiento de mensajes de robots.
        - Avance del tiempo de simulación.
        """
        last_selected = None
        while self.supervisor.step(self.timestep) != -1:
            sel = self.supervisor.getSelected()
            sel_name = sel.getDef() if sel else None

            if sel_name != last_selected:
                self.check_user_selection()
                last_selected = sel_name

            if self.waiting_for_robot:
                self.process_robot_messages()


def main():
    """
    Punto de entrada del programa.
    """
    game = CheckersGame()
    game.run()


if __name__ == "__main__":
    main()
