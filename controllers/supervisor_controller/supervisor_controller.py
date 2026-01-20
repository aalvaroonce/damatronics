"""
supervisor_controller.py - DAMAS PRO: CORONACIÓN PERFECTA
Mejoras:
1. Corona SPAWNEA PLANA (rotación corregida para eje Z).
2. Conector orientado hacia ABAJO para acoplarse.
3. SNAP SINCRONIZADO: Al mover la ficha, la corona se mueve con ella.
"""

from controller import Supervisor
import math

class CheckersGame:
    def __init__(self):
        self.supervisor = Supervisor()
        self.timestep = int(self.supervisor.getBasicTimeStep())
        
        self.emitter = self.supervisor.getDevice('emitter')
        self.receiver = self.supervisor.getDevice('receiver')
        self.receiver.enable(self.timestep)
        
        # Estado del juego
        self.board = [[None for _ in range(8)] for _ in range(8)]
        self.current_team = "WHITE"
        
        self.selected_piece = None
        self.selected_grid = None
        self.waiting_for_robot = False
        self.moving_robot_name = None 
        self.moving_robot_target = None 
        
        self.forced_piece = None 
        
        self.robots = {}
        self.init_robots()
        self.init_board()
        
        print("=== DAMAS 2.0: CORONACIÓN & SNAP PERFECTOS ===")

    def init_robots(self):
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
        for name, robot_info in self.robots.items():
            if robot_info['alive']:
                pos = robot_info['trans_field'].getSFVec3f()
                x, y = self.world_to_grid(pos[0], pos[1])
                if 0 <= x < 8 and 0 <= y < 8:
                    self.board[y][x] = name
        self.print_board()
    
    def world_to_grid(self, world_x, world_y):
        grid_x = int(round((world_x + 0.7) / 0.2))
        grid_y = int(round((world_y + 0.7) / 0.2))
        return grid_x, grid_y
    
    def grid_to_world(self, grid_x, grid_y):
        world_x = -0.7 + grid_x * 0.2
        world_y = -0.7 + grid_y * 0.2
        return world_x, world_y
    
    def print_board(self):
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
        selected_node = self.supervisor.getSelected()
        if selected_node is None: return
        
        node_name = selected_node.getDef()
        if not node_name: return
        
        if node_name in self.robots:
            self.handle_robot_click(node_name)
        elif node_name.startswith("TILE_"):
            parts = node_name.split("_")
            if len(parts) == 3:
                self.handle_tile_click(int(parts[1]), int(parts[2]))

    def handle_robot_click(self, robot_name):
        if self.waiting_for_robot: return
        
        if self.forced_piece and robot_name != self.forced_piece:
            print(f"⚠️ ¡COMBO OBLIGATORIO! Debes seguir usando {self.forced_piece}")
            return
        
        robot_info = self.robots[robot_name]
        if robot_info['team'] != self.current_team:
            print(f"❌ Turno de {self.current_team}")
            return
        if not robot_info['alive']: return
        
        self.selected_piece = robot_name
        for y in range(8):
            for x in range(8):
                if self.board[y][x] == robot_name:
                    self.selected_grid = (x, y)
                    break
        print(f"✅ Seleccionado: {robot_name}")

    def handle_tile_click(self, x, y):
        if self.waiting_for_robot or self.selected_piece is None: return
        
        valid, captured_piece = self.validate_move(self.selected_grid, (x, y))
        
        if valid:
            self.execute_move(self.selected_grid, (x, y), captured_piece)
        else:
            print("❌ Movimiento inválido")
            if not self.forced_piece:
                self.selected_piece = None

    def validate_move(self, origin, destination):
        ox, oy = origin
        dx, dy = destination
        
        if self.board[dy][dx] is not None: return False, None
        
        piece_name = self.board[oy][ox]
        info = self.robots[piece_name]
        team = info['team']
        is_king = info['is_king']
        
        diff_x = dx - ox
        diff_y = dy - oy
        
        if abs(diff_x) != abs(diff_y): return False, None
        
        direction_x = 1 if diff_x > 0 else -1
        direction_y = 1 if diff_y > 0 else -1
        
        if not is_king:
            if abs(diff_x) == 1:
                if self.forced_piece: return False, None
                if team == "WHITE" and diff_y < 0: return False, None
                if team == "BLACK" and diff_y > 0: return False, None
                return True, None
            
            if abs(diff_x) == 2:
                mid_x = ox + direction_x
                mid_y = oy + direction_y
                victim = self.board[mid_y][mid_x]
                if victim and self.robots[victim]['team'] != team:
                    return True, victim
            return False, None

        else: # Flying King logic
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
            
            if victim: return True, victim
            else:
                if self.forced_piece: return False, None
                return True, None

    def can_capture_more(self, piece_name, current_x, current_y):
        info = self.robots[piece_name]
        is_king = info['is_king']
        directions = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        
        if not is_king:
            for dx, dy in directions:
                dest_x, dest_y = current_x + dx*2, current_y + dy*2
                if 0 <= dest_x < 8 and 0 <= dest_y < 8:
                    valid, _ = self.validate_move((current_x, current_y), (dest_x, dest_y))
                    if valid: return True
        else:
            for dx, dy in directions:
                for dist in range(2, 8):
                    dest_x, dest_y = current_x + dx*dist, current_y + dy*dist
                    if 0 <= dest_x < 8 and 0 <= dest_y < 8:
                        valid, victim = self.validate_move((current_x, current_y), (dest_x, dest_y))
                        if valid and victim: return True
                    else:
                        break
        return False

    def execute_move(self, origin, destination, captured_piece):
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

        if captured_piece and not will_promote and self.can_capture_more(piece, dx, dy):
            self.forced_piece = piece
            print(f"🔥 ¡COMBO! {piece} puede seguir comiendo. Turno mantenido.")
        else:
            self.forced_piece = None

        self.selected_piece = None
        self.print_board()

    def promote_king(self, piece_name):
        """
        CORONACIÓN: Spawnea cilindro plano y conector hacia abajo.
        """
        self.robots[piece_name]['is_king'] = True
        
        pos = self.robots[piece_name]['trans_field'].getSFVec3f()
        wx, wy = pos[0], pos[1]
        
        # Calculamos la altura perfecta.
        # Robot (0.05) + Connector (0.085) = 0.135.
        # Ponemos la corona JUSTO ahí.
        spawn_z = 0.135 
        
        print(f"👑 INVOCANDO CORONA para {piece_name}...")
        
        root_children = self.supervisor.getRoot().getField("children")
        crown_def = f"CROWN_{piece_name}"
        
        # 1. rotation 1 0 0 1.5708 -> Rota el cilindro para que el eje Y (su altura) se tumbe.
        #    Ahora la "cara" redonda mira hacia arriba (Eje Z). ¡CORONA PLANA!
        # 2. Connector rotation: Apuntando hacia abajo (-Z) para buscar al del robot.
        
        crown_vrml = f"""
        DEF {crown_def} Solid {{
          translation {wx} {wy} {spawn_z}
          rotation 1 0 0 1.5708 
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
        
        # Forzar el acople
        self.emitter.send(f"{piece_name} LOCK".encode('utf-8'))

    def capture_piece(self, piece_name):
        robot = self.robots[piece_name]
        node = robot['node']
        team = robot['team']
        jump_dir = 1.0 if team == "WHITE" else -1.0
        
        node.setVelocity([
            jump_dir * 40.0,   0.0,   50.0,
            0.0,              50.0,    0.0 
        ])
        robot['alive'] = False
        for y in range(8):
            for x in range(8):
                if self.board[y][x] == piece_name:
                    self.board[y][x] = None
        print(f"🚀☄️ ¡YEET! {piece_name} eliminada.")

    def snap_robot_to_grid(self, robot_name, grid_x, grid_y):
        """
        SNAP MEJORADO: Teletransporta Robot Y Corona juntos.
        """
        robot = self.robots[robot_name]
        node = robot['node']
        target_wx, target_wy = self.grid_to_world(grid_x, grid_y)
        
        # 1. Snap Robot
        node.resetPhysics()
        robot['trans_field'].setSFVec3f([target_wx, target_wy, 0.05])
        robot['rot_field'].setSFRotation([0, 0, 1, 0])
        
        # 2. Snap Corona (Si existe)
        # Esto es crucial para que no se quede atrás al mover la ficha de nuevo
        if robot['is_king']:
            crown_node = self.supervisor.getFromDef(f"CROWN_{robot_name}")
            if crown_node:
                crown_node.resetPhysics()
                # Altura de la corona: Robot (0.05) + Conector (0.085) = 0.135
                crown_node.getField("translation").setSFVec3f([target_wx, target_wy, 0.135])
                # Mantenemos la rotación plana (1 0 0 1.5708)
                crown_node.getField("rotation").setSFRotation([1, 0, 0, 1.5708])
                
        print(f"✨ SNAP: {robot_name} fijado.")

    def process_robot_messages(self):
        while self.receiver.getQueueLength() > 0:
            msg = self.receiver.getString()
            self.receiver.nextPacket()
            parts = msg.split()
            sender = parts[0]
            command = parts[1]
            
            if command == "ARRIVED":
                if sender == self.moving_robot_name:
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
        self.current_team = "BLACK" if self.current_team == "WHITE" else "WHITE"
        print(f"\n🔄 Turno: {self.current_team}")

    def run(self):
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
    game = CheckersGame()
    game.run()

if __name__ == "__main__":
    main()