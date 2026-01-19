"""
Controlador principal para el juego de damas en Webots
Implementa la lógica completa del juego: movimientos, capturas, promoción y turnos

Este controlador maneja toda la lógica del juego de damas, incluyendo:
- Validación de movimientos
- Sistema de capturas (obligatorias y múltiples)
- Promoción a reina
- Detección de fin de juego
- Interacción con el usuario mediante clicks en TouchSensors

Autor: Estudiantes de Ingeniería de Software
Fecha: 2025
"""

from controller import Robot, Supervisor, Node, TouchSensor, Receiver, Emitter
import math
import time

class TableroDamas:
    """
    Clase principal que maneja el estado y lógica del tablero de damas
    """
    
    def __init__(self, supervisor):
        self.supervisor = supervisor
        self.estado_tablero = {}  # dict: (fila, col) -> {'jugador': int, 'es_reina': bool, 'nodo': Node, 'nombre': str}
        self.turno_actual = 1  # 1 o 2 (1=blancas/W, 2=negras/B)
        self.pieza_seleccionada = None  # (fila, col) de la pieza seleccionada
        self.movimientos_validos = []  # lista de (fila, col) válidas para mover
        self.jugando_captura = False  # si estamos en medio de una secuencia de capturas
        self.numero_turno = 1
        self.piezas_capturadas_j1 = 0
        self.piezas_capturadas_j2 = 0
        
        # Mapeo de coordenadas del tablero
        # El tablero va de -0.7 a 0.7 en ambos ejes, con casillas de 0.2m
        # Solo las casillas negras son jugables (donde (fila + col) % 2 == 1)
        
        # IMPORTANTE: Desactivar controladores de todas las piezas ANTES de que se carguen
        # Esto evita que Webots intente cargar el controlador inexistente "robot_driver"
        print("Desactivando controladores de piezas antes de inicializar...")
        self._desactivar_controladores_piezas()
        
        # Dar un paso inicial para que el mundo se cargue completamente
        supervisor.step(int(supervisor.getBasicTimeStep()))
        
        # PAUSAR la simulación ANTES de hacer cambios
        supervisor.simulationSetMode(0)  # 0 = PAUSE
        
        # Inicializar piezas en el tablero
        self._inicializar_piezas()
        
        # Desactivar física de todas las piezas después de inicializarlas
        self._desactivar_fisica_piezas()
        
        # REANUDAR la simulación después de desactivar física
        supervisor.simulationSetMode(1)  # 1 = RUN
        
        print("=== TABLERO DE DAMAS INICIADO ===")
        print(f"Piezas encontradas: {len(self.estado_tablero)}")
        print(f"Turno del Jugador {self.turno_actual} (Turno #{self.numero_turno})")
        self._mostrar_estado()
        
        # Verificar que las piezas sean accesibles
        piezas_accesibles = 0
        for (fila, col), pieza in self.estado_tablero.items():
            try:
                if pieza['nodo']:
                    test = pieza['nodo'].getField("translation")
                    if test:
                        piezas_accesibles += 1
            except:
                pass
        print(f"Piezas accesibles para movimiento: {piezas_accesibles}/{len(self.estado_tablero)}")
    
    def _tile_a_coords(self, tile_name):
        """
        Convierte nombre de TILE (ej: "TILE_2_3") a coordenadas (fila, col)
        """
        try:
            partes = tile_name.split("_")
            if len(partes) >= 3:
                col = int(partes[1])
                fila = int(partes[2])
                return (fila, col)
        except:
            pass
        return None
    
    def _coords_a_posicion_3d(self, fila, col):
        """
        Convierte coordenadas (fila, col) a posición 3D en Webots
        Tablero centrado en (0, 0), casillas de 0.2m, empieza en -0.7
        """
        x = -0.7 + col * 0.2
        y = -0.7 + fila * 0.2
        return (x, y, 0.012)  # z=0.012 para que esté sobre el tablero
    
    def _es_casilla_negra(self, fila, col):
        """
        Verifica si una casilla es negra (jugable)
        En este tablero, las casillas negras son donde (fila + col) % 2 == 0
        (basado en los nombres de los tiles: TILE_0_0, TILE_2_0, TILE_1_1, etc.)
        """
        return (fila + col) % 2 == 0
    
    def _desactivar_controladores_piezas(self):
        """
        Desactiva los controladores de todas las piezas CheckerRobot ANTES de que se carguen
        Esto evita que Webots intente cargar el controlador inexistente "robot_driver"
        """
        try:
            root = self.supervisor.getRoot()
            children_field = root.getField("children")
            if not children_field:
                return
            
            num_nodos = children_field.getCount()
            piezas_desactivadas = 0
            
            for i in range(num_nodos):
                try:
                    nodo = children_field.getMFNode(i)
                    if not nodo:
                        continue
                    
                    try:
                        nombre = nodo.getField("name").getSFString()
                    except:
                        continue
                    
                    if not nombre:
                        continue
                    
                    tipo_nodo = nodo.getTypeName()
                    
                    # Buscar piezas CheckerRobot
                    if (nombre.startswith("W_") or nombre.startswith("B_")) and (tipo_nodo == "CheckerRobot" or tipo_nodo == "Robot"):
                        try:
                            controller_field = nodo.getField("controller")
                            if controller_field:
                                controller_actual = controller_field.getSFString()
                                if controller_actual and controller_actual != "":
                                    controller_field.setSFString("")
                                    piezas_desactivadas += 1
                                    print(f"  ✓ Controlador desactivado para {nombre} (era: {controller_actual})")
                        except Exception as e:
                            print(f"  ⚠ Error desactivando controlador de {nombre}: {e}")
                except:
                    continue
            
            print(f"Controladores desactivados en {piezas_desactivadas} piezas")
        except Exception as e:
            print(f"ERROR en _desactivar_controladores_piezas: {e}")
            import traceback
            traceback.print_exc()
    
    def _inicializar_piezas(self):
        """
        Busca las piezas CheckerRobot en el mundo y las mapea al tablero    
        W_XX = Jugador 1 (blancas), B_XX = Jugador 2 (negras)
        """
        try:
            root_node = self.supervisor.getRoot()
            children_field = root_node.getField("children")
            if not children_field:
                print("⚠ No se pudo obtener children_field del root")
                return
                
            num_nodos = children_field.getCount()
            print(f"Buscando piezas en {num_nodos} nodos del mundo...")
            
            for i in range(num_nodos):
                try:
                    # Verificar que children_field siga siendo válido
                    if not children_field:
                        print(f"⚠ children_field se volvió None en iteración {i}, re-obteniendo...")
                        root_node = self.supervisor.getRoot()
                        children_field = root_node.getField("children")
                        if not children_field:
                            print("⚠ No se pudo re-obtener children_field")
                            break
                    
                    try:
                        nodo = children_field.getMFNode(i)
                    except Exception as e:
                        print(f"DEBUG: Error obteniendo nodo {i}: {e}")
                        continue
                    
                    if not nodo:
                        continue
                    
                    try:
                        nombre_field = nodo.getField("name")
                        if not nombre_field:
                            continue
                        nombre = nombre_field.getSFString()
                    except:
                        continue    
                    
                    if not nombre:
                        continue
                        
                    tipo_nodo = nodo.getTypeName()
                    
                    # Debug: mostrar todos los nodos encontrados
                    if nombre.startswith("W_") or nombre.startswith("B_"):
                        print(f"DEBUG: Encontrado nodo {nombre} de tipo {tipo_nodo}")
                    
                    # Buscar piezas CheckerRobot (pueden ser tipo "CheckerRobot" o "Robot" con nombre W_ o B_)
                    if (nombre.startswith("W_") or nombre.startswith("B_")) and (tipo_nodo == "CheckerRobot" or tipo_nodo == "Robot"):
                        # Obtener posición actual
                        translation_field = nodo.getField("translation")
                        if translation_field:
                            pos = translation_field.getSFVec3f()
                            x, y, z = pos
                            
                            # Convertir posición a coordenadas del tablero
                            # El tablero va de -0.7 a 0.7, con casillas de 0.2m
                            # x corresponde a columna, y corresponde a fila
                            col = round((x + 0.7) / 0.2)
                            fila = round((y + 0.7) / 0.2)
                            
                            print(f"DEBUG: Pieza {nombre} en posición 3D ({x:.3f}, {y:.3f}, {z:.3f}) -> fila={fila}, col={col}")
                            
                            # Solo procesar si está en una casilla válida
                            if 0 <= fila < 8 and 0 <= col < 8:
                                es_negra = self._es_casilla_negra(fila, col)
                                print(f"DEBUG: Casilla ({fila}, {col}) es negra? {es_negra}")
                                if es_negra:
                                    jugador = 1 if nombre.startswith("W_") else 2
                                    
                                    # Desactivar física de la pieza INMEDIATAMENTE (mientras está pausada)
                                    try:
                                        # Desactivar controlador
                                        controller_field = nodo.getField("controller")
                                        if controller_field:
                                            controller_field.setSFString("")
                                        
                                        # ELIMINAR física del Robot principal
                                        robot_physics = nodo.getField("physics")
                                        if robot_physics:
                                            robot_physics.importSFNodeFromString("NULL")
                                        
                                        # ELIMINAR física de todos los Solids internos
                                        try:
                                            children_field = nodo.getField("children")
                                            if children_field:
                                                for j in range(children_field.getCount()):
                                                    try:
                                                        child = children_field.getMFNode(j)
                                                        if child and child.getTypeName() == "Solid":
                                                            child_physics = child.getField("physics")
                                                            if child_physics:
                                                                child_physics.importSFNodeFromString("NULL")
                                                    except:
                                                        continue
                                        except:
                                            pass
                                        
                                        # Desactivar motores
                                        try:
                                            left_motor = nodo.getDevice("left_motor")
                                            if left_motor:
                                                left_motor.setPosition(float('inf'))
                                                left_motor.setVelocity(0.0)
                                        except:
                                            pass
                                        
                                        try:
                                            right_motor = nodo.getDevice("right_motor")
                                            if right_motor:
                                                right_motor.setPosition(float('inf'))
                                                right_motor.setVelocity(0.0)
                                        except:
                                            pass
                                        
                                        # Resetear velocidades
                                        try:
                                            velocity_field = nodo.getField("linearVelocity")
                                            if velocity_field:
                                                velocity_field.setSFVec3f([0.0, 0.0, 0.0])
                                            angular_velocity_field = nodo.getField("angularVelocity")
                                            if angular_velocity_field:
                                                angular_velocity_field.setSFVec3f([0.0, 0.0, 0.0])
                                        except:
                                            pass
                                    except Exception as e:
                                        print(f"⚠ Error desactivando física de {nombre}: {e}")
                                    
                                    self.estado_tablero[(fila, col)] = {
                                        'jugador': jugador,
                                        'es_reina': False,  # Por ahora todas son normales
                                        'nodo': nodo,
                                        'nombre': nombre
                                    }
                                    # Verificar que el nodo sea accesible
                                    try:
                                        test_translation = nodo.getField("translation")
                                        if test_translation:
                                            print(f"✓ Pieza {nombre} encontrada en ({fila}, {col}), jugador {jugador} - Física desactivada")
                                        else:
                                            print(f"⚠ Pieza {nombre} encontrada pero sin campo translation")
                                    except Exception as e:
                                        print(f"⚠ Error accediendo a pieza {nombre}: {e}")
                                else:
                                    print(f"DEBUG: ⚠ Pieza {nombre} NO está en casilla negra ({fila}, {col})")
                            else:
                                print(f"DEBUG: ⚠ Pieza {nombre} está fuera del tablero (fila={fila}, col={col})")
                except Exception as e:
                    print(f"DEBUG: Error procesando pieza: {e}")
                    import traceback
                    traceback.print_exc()
                    # Continuar con el siguiente nodo si hay error
                    continue
        except Exception as e:
            print(f"ERROR en _inicializar_piezas: {e}")
            import traceback
            traceback.print_exc()
    
    def _desactivar_fisica_piezas(self):
        """
        Desactiva la física de todas las piezas para que no se muevan solas
        Se llama después de inicializar todas las piezas
        """
        print("Desactivando física de todas las piezas...")
        piezas_desactivadas = 0
        for (fila, col), pieza in self.estado_tablero.items():
            nodo = pieza['nodo']
            try:
                # IMPORTANTE: Desactivar el controlador del robot para que no se mueva solo
                controller_field = nodo.getField("controller")
                if controller_field:
                    controller_field.setSFString("")  # Sin controlador
                    print(f"  Controlador desactivado para {pieza['nombre']}")
                
                # Desactivar motores PRIMERO (más importante)
                if nodo.getTypeName() == "Robot":
                    try:
                        left_motor = nodo.getDevice("left_motor")
                        if left_motor:
                            left_motor.setPosition(float('inf'))
                            left_motor.setVelocity(0.0)
                            left_motor.setAcceleration(-1)  # Desactivar aceleración
                    except:
                        pass
                    
                    try:
                        right_motor = nodo.getDevice("right_motor")
                        if right_motor:
                            right_motor.setPosition(float('inf'))
                            right_motor.setVelocity(0.0)
                            right_motor.setAcceleration(-1)  # Desactivar aceleración
                    except:
                        pass
                
                # Resetear velocidades para evitar movimiento
                try:
                    # Resetear velocidad lineal
                    velocity_field = nodo.getField("linearVelocity")
                    if velocity_field:
                        velocity_field.setSFVec3f([0.0, 0.0, 0.0])
                    
                    # Resetear velocidad angular
                    angular_velocity_field = nodo.getField("angularVelocity")
                    if angular_velocity_field:
                        angular_velocity_field.setSFVec3f([0.0, 0.0, 0.0])
                except:
                    pass
                
                # DESACTIVAR COMPLETAMENTE la física del Robot
                physics_field = nodo.getField("physics")
                if physics_field:
                    # Eliminar el nodo Physics completamente (ponerlo en NULL)
                    physics_field.importSFNodeFromString("NULL")
                    print(f"  Física del Robot desactivada para {pieza['nombre']}")
                
                # También desactivar física del Solid interno si existe
                try:
                    children_field = nodo.getField("children")
                    if children_field:
                        for i in range(children_field.getCount()):
                            child = children_field.getMFNode(i)
                            if child.getTypeName() == "Solid":
                                child_physics = child.getField("physics")
                                if child_physics:
                                    # Eliminar física del Solid también
                                    child_physics.importSFNodeFromString("NULL")
                                    
                            # Bloquear joints si existen (HingeJoint)
                            if child.getTypeName() == "HingeJoint":
                                try:
                                    # Intentar bloquear el joint
                                    joint_params = child.getField("jointParameters")
                                    if joint_params:
                                        joint_params_node = joint_params.getSFNode()
                                        if joint_params_node:
                                            # Establecer posición mínima y máxima iguales para bloquear
                                            min_stop = joint_params_node.getField("minStop")
                                            max_stop = joint_params_node.getField("maxStop")
                                            if min_stop and max_stop:
                                                # Obtener posición actual y bloquearla
                                                position_field = joint_params_node.getField("position")
                                                if position_field:
                                                    pos = position_field.getSFFloat()
                                                    min_stop.setSFFloat(pos)
                                                    max_stop.setSFFloat(pos)
                                except:
                                    pass
                except:
                    pass
                
                piezas_desactivadas += 1
            except Exception as e:
                print(f"⚠ Error desactivando física de {pieza['nombre']}: {e}")
        print(f"✓ Física desactivada para {piezas_desactivadas} piezas")
    
    def obtener_movimientos_validos(self, fila, col, verificar_capturas_obligatorias=True):
        """
        Obtiene todos los movimientos válidos para una pieza en (fila, col)
        Retorna lista de tuplas: ((fila_dest, col_dest), es_captura, (fila_capt, col_capt))
        
        Args:
            verificar_capturas_obligatorias: Si True, verifica si hay capturas obligatorias
                                            (evita recursión infinita cuando es False)
        """
        if (fila, col) not in self.estado_tablero:
            return []
        
        pieza = self.estado_tablero[(fila, col)]
        jugador = pieza['jugador']
        es_reina = pieza['es_reina']
        
        if jugador != self.turno_actual:
            return []
        
        movimientos = []
        
        # Direcciones posibles
        if es_reina:
            direcciones = [(-1, -1), (-1, 1), (1, -1), (1, 1)]  # Todas las diagonales
        else:
            # Dama normal: solo adelante (jugador 1 hacia arriba, jugador 2 hacia abajo)
            if jugador == 1:  # Blancas (W) - hacia arriba (aumentar fila)
                direcciones = [(1, -1), (1, 1)]
            else:  # Negras (B) - hacia abajo (disminuir fila)
                direcciones = [(-1, -1), (-1, 1)]
        
        # Buscar movimientos simples y capturas
        for df, dc in direcciones:
            # Movimiento simple (una casilla)
            nueva_fila = fila + df
            nueva_col = col + dc
            
            if 0 <= nueva_fila < 8 and 0 <= nueva_col < 8:
                if self._es_casilla_negra(nueva_fila, nueva_col):
                    if (nueva_fila, nueva_col) not in self.estado_tablero:
                        # Movimiento simple válido (solo si no hay capturas obligatorias)
                        if verificar_capturas_obligatorias:
                            hay_capturas = self._hay_capturas_disponibles(jugador)
                            if not hay_capturas:
                                movimientos.append(((nueva_fila, nueva_col), False, None))
                            else:
                                print(f"DEBUG: Movimiento simple desde ({fila}, {col}) a ({nueva_fila}, {nueva_col}) bloqueado por capturas obligatorias")
                        else:
                            # Si no verificamos capturas obligatorias, agregar directamente
                            movimientos.append(((nueva_fila, nueva_col), False, None))
                    # else: casilla ocupada, no es un movimiento válido
                # else: no es casilla negra, no es un movimiento válido
            # else: fuera del tablero, no es un movimiento válido
            
            # Captura (saltar una pieza enemiga)
            nueva_fila = fila + 2 * df
            nueva_col = col + 2 * dc
            
            if 0 <= nueva_fila < 8 and 0 <= nueva_col < 8:
                if self._es_casilla_negra(nueva_fila, nueva_col):
                    casilla_intermedia = (fila + df, col + dc)
                    nueva_casilla = (nueva_fila, nueva_col)
                    
                    if (casilla_intermedia in self.estado_tablero and
                        nueva_casilla not in self.estado_tablero):
                        
                        pieza_intermedia = self.estado_tablero[casilla_intermedia]
                        if pieza_intermedia['jugador'] != jugador:
                            # Captura válida
                            movimientos.append((nueva_casilla, True, casilla_intermedia))
        
        # Si hay capturas, solo retornar capturas (son obligatorias)
        capturas = [m for m in movimientos if m[1]]
        if capturas:
            return capturas
        
        return movimientos
    
    def _hay_capturas_disponibles(self, jugador):
        """
        Verifica si el jugador tiene alguna captura disponible
        """
        for (fila, col), pieza in self.estado_tablero.items():
            if pieza['jugador'] == jugador:
                # Pasar verificar_capturas_obligatorias=False para evitar recursión infinita
                movimientos = self.obtener_movimientos_validos(fila, col, verificar_capturas_obligatorias=False)
                if any(m[1] for m in movimientos):  # Si hay alguna captura
                    return True
        return False
    
    def validar_movimiento(self, origen, destino):
        """
        Valida si un movimiento es válido
        origen y destino son tuplas (fila, col)
        Retorna (es_valido, es_captura, casilla_capturada)
        """
        movimientos = self.obtener_movimientos_validos(origen[0], origen[1])
        for mov in movimientos:
            if mov[0] == destino:
                return (True, mov[1], mov[2])
        return (False, False, None)
    
    def realizar_movimiento(self, origen, destino):
        """
        Realiza un movimiento en el tablero
        origen y destino son tuplas (fila, col)
        Retorna True si fue exitoso, False si no
        """
        es_valido, es_captura, casilla_capturada = self.validar_movimiento(origen, destino)
        
        if not es_valido:
            return False
        
        # Mover la pieza
        pieza = self.estado_tablero[origen].copy()
        del self.estado_tablero[origen]
        self.estado_tablero[destino] = pieza
        
        # Si hay captura, eliminar pieza capturada
        if es_captura and casilla_capturada:
            if casilla_capturada in self.estado_tablero:
                pieza_capturada = self.estado_tablero[casilla_capturada]
                if pieza_capturada['nodo']:
                    try:
                        # Eliminar nodo de la pieza capturada
                        pieza_capturada['nodo'].remove()
                        print(f"¡Pieza capturada en {casilla_capturada}!")
                    except Exception as e:
                        print(f"Error eliminando pieza capturada: {e}")
                del self.estado_tablero[casilla_capturada]
                
                # Actualizar contador de capturas
                if pieza_capturada['jugador'] == 1:
                    self.piezas_capturadas_j1 += 1
                else:
                    self.piezas_capturadas_j2 += 1
        
        # Verificar promoción
        self._verificar_promocion(destino)
        
        # Verificar si hay más capturas posibles desde la nueva posición
        if es_captura:
            nuevas_capturas = self.obtener_movimientos_validos(destino[0], destino[1])
            capturas_posibles = [m for m in nuevas_capturas if m[1]]
            if capturas_posibles:
                # Hay más capturas posibles, el jugador debe continuar
                self.jugando_captura = True
                self.pieza_seleccionada = destino
                self.movimientos_validos = capturas_posibles
                return True
        
        # No hay más capturas, cambiar turno
        self.jugando_captura = False
        self.cambiar_turno()
        return True
    
    def _verificar_promocion(self, posicion):
        """
        Verifica si una pieza debe ser promocionada a reina
        """
        if posicion not in self.estado_tablero:
            return
        
        pieza = self.estado_tablero[posicion]
        if pieza['es_reina']:
            return
        
        fila, col = posicion
        jugador = pieza['jugador']
        
        # Jugador 1 (blancas) promociona en fila 7
        # Jugador 2 (negras) promociona en fila 0
        if (jugador == 1 and fila == 7) or (jugador == 2 and fila == 0):
            pieza['es_reina'] = True
            print(f"¡Pieza promocionada a REINA en {posicion}!")
    
    def cambiar_turno(self):
        """
        Cambia el turno al siguiente jugador
        """
        self.turno_actual = 2 if self.turno_actual == 1 else 1
        self.numero_turno += 1
        self.pieza_seleccionada = None
        self.movimientos_validos = []
        print(f"\n--- Turno del Jugador {self.turno_actual} (Turno #{self.numero_turno}) ---")
        self._mostrar_estado()
    
    def _mostrar_estado(self):
        """
        Muestra el estado actual del juego
        """
        piezas_j1 = sum(1 for p in self.estado_tablero.values() if p['jugador'] == 1)
        piezas_j2 = sum(1 for p in self.estado_tablero.values() if p['jugador'] == 2)
        reinas_j1 = sum(1 for p in self.estado_tablero.values() 
                       if p['jugador'] == 1 and p['es_reina'])
        reinas_j2 = sum(1 for p in self.estado_tablero.values() 
                       if p['jugador'] == 2 and p['es_reina'])
        
        print(f"Jugador 1 (Blancas): {piezas_j1} piezas ({reinas_j1} reinas) | "
              f"Capturadas: {self.piezas_capturadas_j1}")
        print(f"Jugador 2 (Negras): {piezas_j2} piezas ({reinas_j2} reinas) | "
              f"Capturadas: {self.piezas_capturadas_j2}")
    
    def verificar_fin_juego(self):
        """
        Verifica si el juego ha terminado
        Retorna (juego_terminado, ganador)
        """
        # Si no hay piezas en el tablero, el juego no ha terminado (aún no se han inicializado)
        if len(self.estado_tablero) == 0:
            return (False, None)
        
        piezas_j1 = sum(1 for p in self.estado_tablero.values() if p['jugador'] == 1)
        piezas_j2 = sum(1 for p in self.estado_tablero.values() if p['jugador'] == 2)
        
        if piezas_j1 == 0:
            return (True, 2)
        if piezas_j2 == 0:
            return (True, 1)
        
        # Verificar si algún jugador no tiene movimientos
        movimientos_j1 = []
        movimientos_j2 = []
        for (fila, col), pieza in self.estado_tablero.items():
            movs = self.obtener_movimientos_validos(fila, col)
            if pieza['jugador'] == 1:
                movimientos_j1.extend(movs)
            else:
                movimientos_j2.extend(movs)
        
        if self.turno_actual == 1 and not movimientos_j1:
            return (True, 2)
        if self.turno_actual == 2 and not movimientos_j2:
            return (True, 1)
        
        return (False, None)


class DamasController:
    """
    Controlador principal que maneja la interacción con Webots
    """
    
    def __init__(self):
        self.robot = Supervisor()
        self.timestep = int(self.robot.getBasicTimeStep())
        
        # Inicializar tablero
        self.tablero = TableroDamas(self.robot)
        
        # Obtener referencias a nodos del mundo
        self.root_node = self.robot.getRoot()
        self.children_field = self.root_node.getField("children")
        
        # Configurar sensores de interacción
        self._configurar_sensores()
        
        print("\n¡Juego listo! Haz click en las casillas del tablero para jugar.")
    
    def _configurar_sensores(self):
        """
        Configura los sensores y mapea los Tiles del tablero
        """
        self.tiles_map = {}  # Mapeo de nombres de Tiles a coordenadas
        self.touch_sensors = {}  # Mapeo de sensores TouchSensor
        
        # Buscar el Robot que contiene el tablero (game_supervisor)
        num_nodos = self.children_field.getCount()
        print(f"DEBUG: Buscando game_supervisor en {num_nodos} nodos de la raíz...")
        for i in range(num_nodos):
            try:
                nodo = self.children_field.getMFNode(i)
                if not nodo:
                    continue
                
                try:
                    nombre_field = nodo.getField("name")
                    if not nombre_field:
                        continue
                    nombre = nombre_field.getSFString()
                except Exception as e:
                    continue
                
                tipo_nodo = nodo.getTypeName()
                
                # Debug: mostrar nodos encontrados
                if nombre == "game_supervisor":
                    print(f"DEBUG: Encontrado game_supervisor, tipo: {tipo_nodo}")
                
                # Buscar específicamente el Robot llamado "game_supervisor" que contiene las casillas
                if nombre == "game_supervisor" and tipo_nodo == "Robot":
                    print(f"DEBUG: ✓ Encontrado game_supervisor!")
                    # Buscar Tiles dentro de este Robot
                    children_field = nodo.getField("children")
                    if children_field:
                        num_children = children_field.getCount()
                        print(f"DEBUG: game_supervisor tiene {num_children} children")
                        for j in range(num_children):
                            try:
                                child = children_field.getMFNode(j)
                                if not child:
                                    continue
                                
                                try:
                                    child_name_field = child.getField("name")
                                    if not child_name_field:
                                        continue
                                    child_name = child_name_field.getSFString()
                                except:
                                    continue
                                
                                if child_name and child_name.startswith("TILE_"):
                                    print(f"DEBUG: Encontrado tile: {child_name}")
                                    coords = self.tablero._tile_a_coords(child_name)
                                    if coords:
                                        fila, col = coords
                                        self.tiles_map[child_name] = {
                                            'coords': (fila, col),
                                            'tile_node': child
                                        }
                                        
                                        # Buscar TouchSensor dentro del tile
                                        tile_children = child.getField("children")
                                        if tile_children:
                                            for k in range(tile_children.getCount()):
                                                tile_child = tile_children.getMFNode(k)
                                                if tile_child.getTypeName() == "TouchSensor":
                                                    sensor_name = tile_child.getField("name").getSFString()
                                                    if sensor_name:
                                                        try:
                                                            sensor = self.robot.getDevice(sensor_name)
                                                            if sensor:
                                                                sensor.enable(self.timestep)
                                                                self.touch_sensors[sensor_name] = {
                                                                    'sensor': sensor,
                                                                    'coords': (fila, col),
                                                                    'tile_name': child_name
                                                                }
                                                                print(f"TouchSensor {sensor_name} configurado para {child_name} ({fila}, {col})")
                                                        except:
                                                            pass
                                        
                                        print(f"Tile {child_name} mapeado a ({fila}, {col})")
                            except Exception as e:
                                print(f"DEBUG: Error procesando child {j} de game_supervisor: {e}")
                                continue
                    else:
                        print(f"DEBUG: ⚠ game_supervisor no tiene children_field")
                else:
                    # No es game_supervisor, continuar
                    pass
            except Exception as e:
                print(f"ERROR en _configurar_sensores procesando nodo {i}: {e}")
                import traceback
                traceback.print_exc()
                # Continuar con el siguiente nodo si hay error
                continue
        
        print(f"Total de tiles mapeados: {len(self.tiles_map)}")
        print(f"Total de TouchSensors configurados: {len(self.touch_sensors)}")
        
        # Debug: mostrar todos los sensores configurados
        if len(self.touch_sensors) == 0:
            print("⚠ ADVERTENCIA: No se configuraron TouchSensors. Verifica que los tiles tengan TouchSensor dentro.")
        else:
            print("TouchSensors configurados:")
            for sensor_name, sensor_info in self.touch_sensors.items():
                print(f"  - {sensor_name}: {sensor_info['tile_name']} -> {sensor_info['coords']}")
    
    def _mover_pieza_visual(self, origen, destino):
        """
        Mueve visualmente una pieza de una posición a otra
        NOTA: origen es la posición ANTES del movimiento, destino es la posición DESPUÉS
        """
        # La pieza ya está en destino en el estado_tablero después de realizar_movimiento
        if destino not in self.tablero.estado_tablero:
            print(f"ERROR: Destino {destino} no está en estado_tablero")
            return
        
        pieza = self.tablero.estado_tablero.get(destino)
        if not pieza:
            print(f"ERROR: No hay pieza en destino {destino}")
            return
            
        if not pieza['nodo']:
            print(f"ERROR: Pieza en {destino} no tiene nodo asociado")
            return
            
        try:
            pos_destino = self.tablero._coords_a_posicion_3d(destino[0], destino[1])
            
            if not pos_destino:
                print(f"ERROR: No se pudieron calcular coordenadas 3D para destino")
                return
                
            x_dest, y_dest, z_dest = pos_destino
            
            nodo = pieza['nodo']
            campo_translation = nodo.getField("translation")
            if not campo_translation:
                print(f"ERROR: No se pudo obtener campo translation del nodo")
                return
            
            # Asegurar que la física esté desactivada antes de mover
            physics_field = nodo.getField("physics")
            if physics_field:
                physics_node = physics_field.getSFNode()
                if physics_node:
                    physics_field.importSFNodeFromString("NULL")
            
            # Resetear velocidades antes de mover
            try:
                velocity_field = nodo.getField("linearVelocity")
                if velocity_field:
                    velocity_field.setSFVec3f([0.0, 0.0, 0.0])
                angular_velocity_field = nodo.getField("angularVelocity")
                if angular_velocity_field:
                    angular_velocity_field.setSFVec3f([0.0, 0.0, 0.0])
            except:
                pass
                
            print(f"Moviendo pieza {pieza['nombre']} de {origen} a {destino} -> ({x_dest:.3f}, {y_dest:.3f}, {z_dest:.3f})")
            
            # Mover la pieza directamente a la nueva posición usando el supervisor
            # Esto asegura que el movimiento se aplique correctamente
            self.robot.simulationSetMode(0)  # 0 = PAUSE
            campo_translation.setSFVec3f([x_dest, y_dest, z_dest])
            
            # Resetear rotación para que quede recta
            try:
                rotation_field = nodo.getField("rotation")
                if rotation_field:
                    # Rotación neutra: sin rotación
                    rotation_field.setSFRotation([0, 0, 1, 0])
            except:
                pass
            
            # Reanudar simulación
            self.robot.simulationSetMode(1)  # 1 = RUN
            
            # Dar un paso para que el cambio se aplique
            self.robot.step(self.timestep)
            
            print(f"✓ Pieza {pieza['nombre']} movida a {destino}")
        except Exception as e:
            print(f"ERROR moviendo pieza visualmente: {e}")
            import traceback
            traceback.print_exc()
            # Asegurar que la simulación se reanude incluso si hay error
            try:
                self.robot.simulationSetMode(1)  # 1 = RUN
            except:
                pass
    
    def _resaltar_casilla(self, coords, resaltar=True):
        """
        Resalta una casilla cambiando su color
        Los tiles son Solid con Shape dentro
        """
        print(f"DEBUG: _resaltar_casilla llamado con coords={coords}, resaltar={resaltar}")
        
        # Buscar el tile correspondiente a estas coordenadas
        tile_encontrado = False
        for tile_name, tile_info in self.tiles_map.items():
            if tile_info['coords'] == coords:
                tile_encontrado = True
                tile_node = tile_info['tile_node']
                print(f"DEBUG: Tile encontrado: {tile_name} para coords {coords}")
                
                try:
                    # El tile es un Solid, buscar Shape en sus children
                    children_field = tile_node.getField("children")
                    if not children_field:
                        print(f"DEBUG: ⚠ Tile {tile_name} no tiene children_field")
                        continue
                    
                    print(f"DEBUG: Tile {tile_name} tiene {children_field.getCount()} children")
                    shape_encontrado = False
                    for i in range(children_field.getCount()):
                        child = children_field.getMFNode(i)
                        if not child:
                            continue
                        
                        child_type = child.getTypeName()
                        print(f"DEBUG: Child {i}: tipo {child_type}")
                        
                        if child_type == "Shape":
                            shape_encontrado = True
                            print(f"DEBUG: ✓ Shape encontrado en child {i}")
                            appearance_field = child.getField("appearance")
                            if not appearance_field:
                                print(f"DEBUG: ⚠ Shape no tiene appearance_field")
                                continue
                            
                            appearance = appearance_field.getSFNode()
                            if not appearance:
                                print(f"DEBUG: ⚠ appearance_field es None")
                                continue
                            
                            print(f"DEBUG: Appearance encontrado, tipo: {appearance.getTypeName()}")
                            base_color = appearance.getField("baseColor")
                            if not base_color:
                                print(f"DEBUG: ⚠ Appearance no tiene baseColor")
                                continue
                            
                            if resaltar:
                                base_color.setSFColor([0.0, 1.0, 0.0])  # Verde brillante
                                print(f"✓ Casilla {coords} ({tile_name}) resaltada en VERDE")
                            else:
                                base_color.setSFColor([0.1, 0.1, 0.1])  # Negro original
                                print(f"✓ Casilla {coords} ({tile_name}) restaurada a NEGRO")
                            return
                    
                    if not shape_encontrado:
                        print(f"DEBUG: ⚠ No se encontró Shape en tile {tile_name}")
                except Exception as e:
                    print(f"ERROR resaltando casilla {coords}: {e}")
                    import traceback
                    traceback.print_exc()
                break
        
        if not tile_encontrado:
            print(f"DEBUG: ⚠ No se encontró tile para coords {coords}")
            print(f"DEBUG: Tiles disponibles: {list(self.tiles_map.keys())[:5]}...")
    
    def procesar_click_tile(self, fila, col):
        """
        Procesa un click en una casilla del tablero
        """
        print(f"DEBUG: procesar_click_tile llamado con ({fila}, {col})")
        print(f"DEBUG: Es casilla negra? {self.tablero._es_casilla_negra(fila, col)}")
        print(f"DEBUG: Estado del tablero: {len(self.tablero.estado_tablero)} piezas")
        print(f"DEBUG: Turno actual: {self.tablero.turno_actual}")
        
        if not self.tablero._es_casilla_negra(fila, col):
            print(f"DEBUG: Casilla ({fila}, {col}) no es negra, ignorando click")
            return
        
        if self.tablero.jugando_captura:
            # Si estamos en medio de capturas, solo aceptar movimientos de captura
            if self.tablero.pieza_seleccionada is not None:
                destinos_validos = [m[0] for m in self.tablero.movimientos_validos]
                if (fila, col) in destinos_validos:
                    if self.tablero.realizar_movimiento(
                        self.tablero.pieza_seleccionada, (fila, col)
                    ):
                        self._mover_pieza_visual(
                            self.tablero.pieza_seleccionada, (fila, col)
                        )
                        if not self.tablero.jugando_captura:
                            # Quitar resaltado de todas las casillas
                            for mov in self.tablero.movimientos_validos:
                                self._resaltar_casilla(mov[0], False)
                    return
        
        # Si hay una pieza seleccionada, intentar mover
        if self.tablero.pieza_seleccionada is not None:
            destinos_validos = [m[0] for m in self.tablero.movimientos_validos]
            if (fila, col) in destinos_validos:
                # Mover la pieza
                if self.tablero.realizar_movimiento(
                    self.tablero.pieza_seleccionada, (fila, col)
                ):
                    self._mover_pieza_visual(
                        self.tablero.pieza_seleccionada, (fila, col)
                    )
                    # Quitar resaltado
                    for mov in self.tablero.movimientos_validos:
                        self._resaltar_casilla(mov[0], False)
            else:
                # Click en casilla inválida, deseleccionar
                for mov in self.tablero.movimientos_validos:
                    self._resaltar_casilla(mov[0], False)
                self.tablero.pieza_seleccionada = None
                self.tablero.movimientos_validos = []
                print("Movimiento inválido, pieza deseleccionada")
        else:
            # Seleccionar pieza si hay una en esta casilla
            print(f"DEBUG: Buscando pieza en ({fila}, {col})")
            print(f"DEBUG: Piezas en tablero: {list(self.tablero.estado_tablero.keys())}")
            if (fila, col) in self.tablero.estado_tablero:
                pieza = self.tablero.estado_tablero[(fila, col)]
                print(f"DEBUG: Pieza encontrada: jugador {pieza['jugador']}, turno actual: {self.tablero.turno_actual}")
                if pieza['jugador'] == self.tablero.turno_actual:
                    self.tablero.pieza_seleccionada = (fila, col)
                    print(f"DEBUG: Obteniendo movimientos válidos para pieza en ({fila}, {col})")
                    self.tablero.movimientos_validos = (
                        self.tablero.obtener_movimientos_validos(fila, col)
                    )
                    casillas_validas = [m[0] for m in self.tablero.movimientos_validos]
                    
                    print(f"DEBUG: Movimientos válidos obtenidos: {len(casillas_validas)}")
                    print(f"DEBUG: Lista completa de movimientos: {self.tablero.movimientos_validos}")
                    
                    if casillas_validas:
                        # Resaltar casillas válidas
                        print(f"\n{'='*60}")
                        print(f"✓ Pieza seleccionada en ({fila}, {col})")
                        print(f"Movimientos válidos: {casillas_validas}")
                        print(f"DEBUG: Resaltando {len(casillas_validas)} casillas válidas...")
                        for casilla in casillas_validas:
                            print(f"DEBUG: Intentando resaltar casilla {casilla}")
                            self._resaltar_casilla(casilla, True)
                        print(f"DEBUG: Resaltado completado")
                        print(f"{'='*60}\n")
                    else:
                        print(f"⚠ Pieza en ({fila}, {col}) no tiene movimientos válidos")
                        print(f"DEBUG: Verificando por qué no hay movimientos...")
                        # Debug adicional
                        pieza_info = self.tablero.estado_tablero[(fila, col)]
                        print(f"DEBUG: Pieza info: jugador={pieza_info['jugador']}, es_reina={pieza_info['es_reina']}")
                        print(f"DEBUG: Turno actual: {self.tablero.turno_actual}")
                        # Intentar obtener movimientos sin verificar capturas obligatorias
                        movs_sin_verificar = self.tablero.obtener_movimientos_validos(fila, col, verificar_capturas_obligatorias=False)
                        print(f"DEBUG: Movimientos sin verificar capturas: {len(movs_sin_verificar)}")
                        if movs_sin_verificar:
                            print(f"DEBUG: Movimientos encontrados: {[m[0] for m in movs_sin_verificar]}")
                else:
                    print(f"⚠ No es tu turno. Turno actual: Jugador {self.tablero.turno_actual}, pieza: Jugador {pieza['jugador']}")
            else:
                print(f"⚠ Casilla ({fila}, {col}) está vacía")
    
    def run(self):
        """
        Loop principal del controlador
        """
        print("\n" + "="*50)
        print("=== TABLERO DE DAMAS - INSTRUCCIONES ===")
        print("="*50)
        print("1. Haz click IZQUIERDO en una casilla negra para seleccionar/mover")
        print("2. Las casillas válidas se resaltarán en verde")
        print("3. Haz click en una casilla válida para mover")
        print("4. Las capturas son obligatorias si están disponibles")
        print("5. Las piezas se promocionan a reina al llegar al final")
        print("6. Gana el jugador que capture todas las piezas del oponente")
        print("="*50)
        print("El controlador está activo y monitoreando el juego...")
        print(f"Tiles mapeados: {len(self.tiles_map)}\n")
        
        ultimo_nodo_seleccionado = None
        
        # Mantener el controlador activo
        while self.robot.step(self.timestep) != -1:
            # Mantener las piezas estáticas (resetear velocidades continuamente y asegurar física desactivada)
            # PERO solo si no estamos en medio de un movimiento
            for (fila, col), pieza in self.tablero.estado_tablero.items():
                nodo = pieza['nodo']
                try:
                    # Asegurar que la física esté desactivada
                    physics_field = nodo.getField("physics")
                    if physics_field:
                        physics_node = physics_field.getSFNode()
                        if physics_node:  # Si aún tiene física, eliminarla
                            physics_field.importSFNodeFromString("NULL")
                    
                    # Resetear velocidades para evitar movimiento (solo si no está siendo movida)
                    velocity_field = nodo.getField("linearVelocity")
                    if velocity_field:
                        current_vel = velocity_field.getSFVec3f()
                        # Solo resetear si tiene velocidad significativa
                        if abs(current_vel[0]) > 0.001 or abs(current_vel[1]) > 0.001 or abs(current_vel[2]) > 0.001:
                            velocity_field.setSFVec3f([0.0, 0.0, 0.0])
                    
                    angular_velocity_field = nodo.getField("angularVelocity")
                    if angular_velocity_field:
                        current_ang_vel = angular_velocity_field.getSFVec3f()
                        # Solo resetear si tiene velocidad angular significativa
                        if abs(current_ang_vel[0]) > 0.001 or abs(current_ang_vel[1]) > 0.001 or abs(current_ang_vel[2]) > 0.001:
                            angular_velocity_field.setSFVec3f([0.0, 0.0, 0.0])
                    
                    # Mantener motores desactivados
                    if nodo.getTypeName() == "Robot":
                        try:
                            left_motor = nodo.getDevice("left_motor")
                            if left_motor:
                                left_motor.setVelocity(0.0)
                        except:
                            pass
                        
                        try:
                            right_motor = nodo.getDevice("right_motor")
                            if right_motor:
                                right_motor.setVelocity(0.0)
                        except:
                            pass
                except:
                    pass
            
            # Verificar fin de juego
            juego_terminado, ganador = self.tablero.verificar_fin_juego()
            if juego_terminado:
                print(f"\n{'='*30}")
                print(f"¡JUEGO TERMINADO!")
                print(f"¡Ganador: Jugador {ganador}!")
                print(f"{'='*30}")
                self.robot.simulationSetMode(0)  # 0 = PAUSE
                break
            
            # Procesar TouchSensors (método más confiable para clicks)
            for sensor_name, sensor_info in self.touch_sensors.items():
                try:
                    sensor = sensor_info['sensor']
                    sensor_value = sensor.getValue()
                    if sensor_value > 0:  # Sensor activado (click)
                        fila, col = sensor_info['coords']
                        print(f"\n{'='*60}")
                        print(f">>> CLICK DETECTADO en {sensor_info['tile_name']} -> ({fila}, {col})")
                        print(f">>> Valor del sensor: {sensor_value}")
                        print(f">>> Estado del tablero: {len(self.tablero.estado_tablero)} piezas")
                        print(f">>> Turno actual: Jugador {self.tablero.turno_actual}")
                        print(f"{'='*60}")
                        self.procesar_click_tile(fila, col)
                        # Esperar a que el sensor se desactive
                        while sensor.getValue() > 0:
                            self.robot.step(self.timestep)
                        break  # Solo procesar un click a la vez
                except Exception as e:
                    print(f"ERROR procesando sensor {sensor_name}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            # Debug: mostrar estado cada 100 pasos (solo para depuración)
            if self.robot.getTime() % 1.0 < 0.032:  # Aproximadamente cada segundo
                if len(self.touch_sensors) == 0:
                    print("⚠ ADVERTENCIA: No hay TouchSensors configurados. Los clicks no se detectarán.")
                if len(self.tablero.estado_tablero) == 0:
                    print("⚠ ADVERTENCIA: No hay piezas en el tablero. Verifica que las piezas se inicializaron correctamente.")


# Punto de entrada principal
if __name__ == "__main__":
    controller = DamasController()
    controller.run()
