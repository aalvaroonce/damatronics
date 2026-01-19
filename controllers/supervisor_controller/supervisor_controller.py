"""
supervisor_controller.py - Sistema con Click de Mouse
Instrucciones: 
1. Ctrl+Click en un robot para seleccionarlo
2. Ctrl+Click en una casilla destino para moverlo
"""

from controller import Supervisor
import math

class CheckersGame:
    def __init__(self):
        self.supervisor = Supervisor()
        self.timestep = int(self.supervisor.getBasicTimeStep())
        
        self.emitter = self.supervisor.getDevice('emitter')
        
        # Estado del juego
        self.board = [[None for _ in range(8)] for _ in range(8)]
        self.current_team = "WHITE"
        self.selected_piece = None  # Nombre del robot seleccionado
        self.selected_grid = None   # (x, y) en el tablero
        self.waiting_for_robot = False
        
        # Referencias a nodos
        self.robots = {}
        self.tiles = {}  # Casillas del tablero
        
        self.init_robots()
        self.init_tiles()
        self.init_board()
        
        print("=== JUEGO DE DAMAS ROBÓTICAS ===")
        print("📌 CONTROLES:")
        print("  1. Ctrl+Click en un robot para seleccionarlo")
        print("  2. Ctrl+Click en una casilla negra para moverlo")
        print(f"\n🎮 Turno inicial: {self.current_team}\n")
    
    def init_robots(self):
        """Inicializa referencias a robots"""
        white_names = [f"W_{i:02d}" for i in range(1, 13)]
        black_names = [f"B_{i:02d}" for i in range(1, 13)]
        
        for name in white_names + black_names:
            robot_node = self.supervisor.getFromDef(name)
            if robot_node:
                self.robots[name] = {
                    'node': robot_node,
                    'team': 'WHITE' if name.startswith('W') else 'BLACK',
                    'is_king': False,
                    'alive': True
                }
    
    def init_tiles(self):
        """Inicializa referencias a las casillas del tablero"""
        # Casillas negras del tablero
        tile_coords = [
            (0, 0), (2, 0), (4, 0), (6, 0),
            (1, 1), (3, 1), (5, 1), (7, 1),
            (0, 2), (2, 2), (4, 2), (6, 2),
            (1, 3), (3, 3), (5, 3), (7, 3),
            (0, 4), (2, 4), (4, 4), (6, 4),
            (1, 5), (3, 5), (5, 5), (7, 5),
            (0, 6), (2, 6), (4, 6), (6, 6),
            (1, 7), (3, 7), (5, 7), (7, 7)
        ]
        
        for x, y in tile_coords:
            tile_name = f"TILE_{x}_{y}"
            tile_node = self.supervisor.getFromDef(tile_name)
            if tile_node:
                self.tiles[(x, y)] = tile_node
    
    def init_board(self):
        """Escanea posiciones iniciales"""
        for name, robot_info in self.robots.items():
            if robot_info['alive']:
                pos = robot_info['node'].getPosition()
                x, y = self.world_to_grid(pos[0], pos[1])
                if 0 <= x < 8 and 0 <= y < 8:
                    self.board[y][x] = name
        self.print_board()
    
    def world_to_grid(self, world_x, world_y):
        """Convierte coordenadas mundo a grid (0-7)"""
        grid_x = int(round((world_x + 0.7) / 0.2))
        grid_y = int(round((world_y + 0.7) / 0.2))
        return grid_x, grid_y
    
    def grid_to_world(self, grid_x, grid_y):
        """Convierte grid (0-7) a coordenadas mundo"""
        world_x = -0.7 + grid_x * 0.2
        world_y = -0.7 + grid_y * 0.2
        return world_x, world_y
    
    def print_board(self):
        """Imprime tablero en consola"""
        print("\n=== TABLERO ===")
        for y in range(7, -1, -1):
            row = []
            for x in range(8):
                piece = self.board[y][x]
                if piece:
                    symbol = piece[0] + piece[-2:]
                    if piece == self.selected_piece:
                        symbol = f"[{symbol}]"  # Marcar seleccionado
                    row.append(symbol)
                else:
                    row.append("  .")
            print(f"{y}: " + " ".join(row))
        print("   " + " ".join([f"  {i}" for i in range(8)]))
        print()
    
    def check_user_selection(self):
        """Detecta clicks del usuario en robots o casillas"""
        # Obtener el nodo seleccionado por el usuario (Ctrl+Click)
        selected_node = self.supervisor.getSelected()
        
        if selected_node is None:
            return
        
        node_name = selected_node.getDef()
        
        if not node_name:
            return
        
        # ¿Es un robot?
        if node_name in self.robots:
            self.handle_robot_click(node_name)
        
        # ¿Es una casilla?
        elif node_name.startswith("TILE_"):
            parts = node_name.split("_")
            if len(parts) == 3:
                try:
                    x, y = int(parts[1]), int(parts[2])
                    self.handle_tile_click(x, y)
                except ValueError:
                    pass
    
    def handle_robot_click(self, robot_name):
        """Maneja click en un robot"""
        if self.waiting_for_robot:
            print("⏳ Esperando movimiento actual...")
            return
        
        robot_info = self.robots[robot_name]
        
        # Verificar que sea del equipo correcto
        if robot_info['team'] != self.current_team:
            print(f"❌ No puedes mover piezas {robot_info['team']}. Turno de {self.current_team}")
            return
        
        if not robot_info['alive']:
            print(f"❌ {robot_name} está fuera de juego")
            return
        
        # Seleccionar pieza
        self.selected_piece = robot_name
        
        # Encontrar posición en el tablero
        for y in range(8):
            for x in range(8):
                if self.board[y][x] == robot_name:
                    self.selected_grid = (x, y)
                    break
        
        print(f"✅ Seleccionado: {robot_name} ({self.current_team}) en {self.selected_grid}")
        self.print_board()
    
    def handle_tile_click(self, x, y):
        """Maneja click en una casilla"""
        if self.waiting_for_robot:
            print("⏳ Esperando movimiento actual...")
            return
        
        if self.selected_piece is None:
            print("❌ Primero selecciona una pieza")
            return
        
        print(f"🎯 Destino seleccionado: ({x}, {y})")
        
        # Validar y ejecutar movimiento
        if self.validate_move(self.selected_grid, (x, y)):
            self.execute_move(self.selected_grid, (x, y))
        else:
            print("❌ Movimiento inválido")
        
        self.selected_piece = None
        self.selected_grid = None
    
    def validate_move(self, origin, destination):
        """Valida movimiento según reglas"""
        if origin is None or destination is None:
            return False
        
        ox, oy = origin
        dx, dy = destination
        
        # Destino ocupado
        if self.board[dy][dx] is not None:
            print("❌ Casilla ocupada")
            return False
        
        piece_name = self.board[oy][ox]
        robot_info = self.robots[piece_name]
        team = robot_info['team']
        is_king = robot_info['is_king']
        
        delta_x = dx - ox
        delta_y = dy - oy
        
        # Movimiento diagonal
        if abs(delta_x) != abs(delta_y):
            print("❌ Solo movimientos diagonales")
            return False
        
        # Movimiento simple (1 casilla)
        if abs(delta_x) == 1:
            if not is_king:
                if team == "WHITE" and delta_y <= 0:
                    print("❌ Blancas avanzan hacia arriba")
                    return False
                if team == "BLACK" and delta_y >= 0:
                    print("❌ Negras avanzan hacia abajo")
                    return False
            return True
        
        # Captura (2 casillas)
        elif abs(delta_x) == 2:
            mid_x = (ox + dx) // 2
            mid_y = (oy + dy) // 2
            mid_piece = self.board[mid_y][mid_x]
            
            if mid_piece and self.robots[mid_piece]['team'] != team:
                print(f"🎯 Captura: {mid_piece}")
                return True
            else:
                print("❌ No hay enemigo para capturar")
                return False
        
        print("❌ Movimiento demasiado largo")
        return False
    
    def execute_move(self, origin, destination):
        """Ejecuta movimiento validado"""
        ox, oy = origin
        dx, dy = destination
        
        piece_name = self.board[oy][ox]
        
        # Captura
        if abs(dx - ox) == 2:
            mid_x = (ox + dx) // 2
            mid_y = (oy + dy) // 2
            captured = self.board[mid_y][mid_x]
            self.capture_piece(captured)
        
        # Mover
        world_x, world_y = self.grid_to_world(dx, dy)
        message = f"{piece_name} MOVE {world_x:.3f} {world_y:.3f}"
        self.emitter.send(message.encode('utf-8'))
        print(f"📡 {message}")
        
        # Actualizar tablero
        self.board[dy][dx] = piece_name
        self.board[oy][ox] = None
        
        # Coronación
        if (self.robots[piece_name]['team'] == "WHITE" and dy == 7) or \
           (self.robots[piece_name]['team'] == "BLACK" and dy == 0):
            self.crown_piece(piece_name)
        
        self.waiting_for_robot = True
        self.print_board()
    
    def capture_piece(self, piece_name):
        """Captura una pieza"""
        print(f"💀 {piece_name} capturado")
        
        cemetery_x = 1.5 if self.robots[piece_name]['team'] == "WHITE" else -1.5
        message = f"{piece_name} DIE {cemetery_x:.3f} 0.0"
        self.emitter.send(message.encode('utf-8'))
        
        self.robots[piece_name]['alive'] = False
        
        for y in range(8):
            for x in range(8):
                if self.board[y][x] == piece_name:
                    self.board[y][x] = None
    
    def crown_piece(self, piece_name):
        """Corona una pieza"""
        print(f"👑 ¡{piece_name} es ahora Reina!")
        self.robots[piece_name]['is_king'] = True
        
        message = f"{piece_name} LOCK"
        self.emitter.send(message.encode('utf-8'))
    
    def switch_turn(self):
        """Cambia turno"""
        self.current_team = "BLACK" if self.current_team == "WHITE" else "WHITE"
        print(f"\n🔄 Turno: {self.current_team}\n")
        self.waiting_for_robot = False
    
    def run(self):
        """Loop principal"""
        step_counter = 0
        # Inicializamos con Strings vacíos o None
        last_selected_name = None 
        
        while self.supervisor.step(self.timestep) != -1:
            step_counter += 1
            
            # Detectar selección del usuario
            current_selected_node = self.supervisor.getSelected()
            current_selected_name = None

            # Si hay algo seleccionado, obtenemos su nombre (DEF o Name)
            if current_selected_node:
                current_selected_name = current_selected_node.getDef()

            # Comparamos NOMBRES (texto), no objetos
            if current_selected_name != last_selected_name:
                self.check_user_selection()
                last_selected_name = current_selected_name
            
            # Simular fin de movimiento (5 seg)
            if self.waiting_for_robot and step_counter % 300 == 0:
                self.switch_turn()

def main():
    game = CheckersGame()
    game.run()

if __name__ == "__main__":
    main()