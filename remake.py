import asyncio
import json
import os
import socket
import websockets
import time
import secrets
import threading
import logging
from queue import Queue
from movement_control.mouvement_control import MovementControl
import beacon_detection.camera_Api as camera
import control_logic_tracking.auto as auto
import web_control_interface.HTTP_server as http_srv

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Suppress websockets library DEBUG logs to avoid camera frame spam
logging.getLogger('websockets.server').setLevel(logging.WARNING)
logging.getLogger('websockets.protocol').setLevel(logging.WARNING)


class Server():
    def __init__(self,robot):
        logger.info("Initializing Server instance")
        self.latest_frame=None
        self.stop_event =threading.Event() #élément asyncio pour vérifier s il faut arrêter le serveur
        self.connected_clients = set()
        self.robot = robot   #robot a controler
        self.stop_timer =None
        self.auto_mode_active = False #Vérifie si le robot est en mode automatique
        self.battery =100
        self.key =1234  #clé de sécurité pour se connecter au serveur
        self.message_queue = Queue()  # Queue for thread-to-websocket communication
        self.clients_lock = threading.Lock()
        logger.debug(f"Server initialized - auto_mode_active: {self.auto_mode_active}, battery: {self.battery}")

    def calibrage_vitesse(self,speed, rapport):
        ms = 0
            #récupère la vitesse rapportée à la vitesse maximale en fonction du mode
        if rapport == 1: #  => mode lent
            ms = 100
        elif rapport == 2: # ==> mode normal
            ms = 300
        else: # ==> mode sport
            ms = 400
        result = ms * speed
        logger.debug(f"Speed calibration - input: speed={speed}, rapport={rapport}, base_ms={ms}, result={result}")
        return result

    def camera_loop(self):
        logger.info("Camera loop started")
        frame_count = 0
        while True:
            last = camera.get_camera_frame_base64()
            if self.stop_event is not None and self.stop_event.is_set():
                logger.info("Camera loop stop event detected")
                break
            if last is not None and last != self.latest_frame:
                self.latest_frame= last
                frame_count += 1
                response = {"type": "camera_frame", "frame": self.latest_frame}
                self.send_to_all_clients(response)
            time.sleep(0.02)
        logger.info("Camera loop stopped")


    def batterie(self):
        '''
        Récupère la batterie
        '''
        logger.info("Battery monitoring loop started")
        while True:
            if self.stop_event is not None and self.stop_event.is_set():
                logger.info("Battery loop stop event detected")
                break
            # nb = get_battery()
            nb =1
            if nb is not None and nb != self.battery:
                    old_battery = self.battery
                    self.battery= nb
                    logger.info(f"Battery level changed: {old_battery} -> {self.battery}")
                    response = {"type": "battery", "value": self.battery}
                    self.send_to_all_clients(response)
            time.sleep(0.1)
        logger.info("Battery monitoring loop stopped")


    def stop_after_delay(self):
        '''
        Arrête le robot si rien ne se passe après 5 secondes
        '''
        logger.debug("Stop after delay timer started (5s)")
        time.sleep(5)
        logger.info("Stop after delay timer expired - stopping robot")
        self.robot.stop()

    def send_to_all_clients(self,msg):
        '''
            Envoie un message à tous les clients connectés au serveur

            arguments
                msg:  message à envoyer DICTIONNAIRE

        '''
        # Queue message for WebSocket thread to send
        self.message_queue.put(msg)

    async def _async_send_to_all_clients(self,msg):
        '''
            Internal async method to actually send to WebSocket clients
        '''
        with self.clients_lock:
            if self.connected_clients:
                data = json.dumps(msg)
                await asyncio.gather(*(client.send(data) for client in self.connected_clients), return_exceptions=True)

    async def control(self,websocket, path):
        '''
            Fournit l'ensemble des commandes sur la durée d'utilisation du serveur par l'utilisateur

            arguments
                websocket:  fournit les méthodes pour envoyer/recevoir des messages
                path:  le chemin URL du client STRING

        '''
        client_addr = websocket.remote_address
        logger.info(f"New client connected to control - address: {client_addr}, path: {path}")
        with self.clients_lock:
            self.connected_clients.add(websocket) # Récupérer l'adresse de l'utilisateur
            logger.debug(f"Client added to connected_clients - total clients: {len(self.connected_clients)}")
        try:
            async for message in websocket:
                data = json.loads(message)
                message_type = data.get("type")

                if message_type == "command":
                    # Déplacements manuel du robot
                    logger.debug(f"Received 'command' message - auto_mode_active: {self.auto_mode_active}")
                    if self.auto_mode_active:
                        logger.warning("Command rejected - auto mode is active")
                        response = {"type": "error", "error": "Mode auto actif, commandes désactivées"}
                    else:
                        angle = data.get("angle")
                        speed = data.get("distance", 100)
                        x = data.get("x")
                        y = data.get("y")
                        mode = data.get("mode", 1)
                        logger.debug(f"Command parameters - angle: {angle}, speed: {speed}, x: {x}, y: {y}, mode: {mode}")

                        ms = self.calibrage_vitesse(speed, mode)
                        md = 0
                        mg = 0
                        #définit la vitesse à laquelle chaqque roues bouges
                        if angle > 180:
                            angle -= 360

                        if angle == 0 and speed == 0: # pas de mouvement si joystick neutre
                            self.robot.stop()

                        if -90 < angle < 90 :
                            mx = abs(self.calibrage_vitesse(x, mode))
                            my = abs(self.calibrage_vitesse(y, mode))
                        else :
                            mx = -abs(self.calibrage_vitesse(x, mode))
                            my = -abs(self.calibrage_vitesse(y, mode))

                        if 0 < angle < 180 :
                            mg = mx
                            md = my
                        else :
                            mg = my
                            md = mx

                        #avance de mx de la roue droite et my de la roue gauche
                        logger.info(f"Executing robot movement - motor_left: {mg}, motor_right: {md}")
                        self.robot.move_custom(mg,md)

                        # Arrête le mouvement après 3 itérations si plus de commande reçue
                        if self.stop_timer is not None:
                            self.stop_timer.cancel()
                            logger.debug("Previous stop timer cancelled")
                        self.stop_timer = threading.Timer(5.0, self.robot.stop)
                        self.stop_timer.daemon = True
                        self.stop_timer.start()
                        logger.debug("New stop timer started (5s)")
                        response = {"type": "command", "status": "command received","speed":ms }

                elif message_type == "start_auto":
                    #Déplacement automatique du robot
                    logger.info(f"Received 'start_auto' message - current auto_mode_active: {self.auto_mode_active}")
                    if not self.auto_mode_active:
                        init_pos = data.get("init_pos", {})
                        x = init_pos.get("x", 0)
                        y = init_pos.get("y", 0)
                        logger.info(f"Starting auto mode - initial position: x={x}, y={y}")
                        self.auto_mode_active = True
                        response = {"type": "auto_started", "msg": "Mode auto activé"}
                        # Start auto mode in a separate thread
                        logger.debug("Launching auto mode thread")
                        auto_thread = threading.Thread(target=auto.run_second_algo, args=(self.send_to_all_clients,x,y,self.robot), daemon=True)
                        auto_thread.start()
                        logger.info("Auto mode thread started successfully")
                    else:
                        logger.warning("Auto mode start rejected - already active")
                        response = {"type": "error", "msg": "Mode auto déjà actif"}

                elif message_type == "stop_server":
                    logger.warning("Received 'stop_server' message - initiating server shutdown")
                    response = {"type": "server_stopped", "msg": "Serveur arrêté"}
                    await websocket.send(json.dumps(response))
                    logger.info("Stop event set - server will shutdown")
                    self.stop_event.set()
                    await websocket.close()
                    return


                else:
                    logger.warning(f"Unknown message type received: {message_type}")
                    response = {"type": "error", "error": f"Unknown message type: {message_type}"}
                await websocket.send(json.dumps(response))

        except websockets.ConnectionClosed:
            logger.info(f"WebSocket connection closed for client: {client_addr}")
        except Exception as e:
            logger.error(f"Error in control loop for client {client_addr}: {e}", exc_info=True)
        finally:
            with self.clients_lock:
                self.connected_clients.discard(websocket)
                logger.debug(f"Client removed from connected_clients - remaining: {len(self.connected_clients)}")

    async def handler(self,websocket, path):
        '''
            Vérifie si l'utilisateur transmet bien la clé de sécurité avant de le laisser utiliser les commandes

            arguments
                websocket:  fournit les méthodes pour envoyer/recevoir des messages
                path:  le chemin URL du client STRING

        '''
        global key
        key ="1234"
        client_addr = websocket.remote_address
        logger.info(f"New connection attempt - client: {client_addr}, path: {path}")
        try:
            async for message in websocket:
                data = json.loads(message)
                message_type = data.get("type")
                if message_type == "key":
                    value = data.get("value")
                    if value == key:
                        logger.info(f"Authentication successful for client: {client_addr}")
                        response = {"type": "connexion", "body": f"bonne cle connexion au serveur"}

                        await websocket.send(json.dumps(response))
                        await self.control(websocket, path)
                    else :
                        logger.warning(f"Authentication failed for client: {client_addr} - incorrect key")
                        response = {"type": "error", "error": f"Mauvaise cle de securite"}
                        await websocket.send(json.dumps(response))
                else :
                    logger.warning(f"Authentication required for client: {client_addr} - no key provided")
                    response = {"type": "error", "error": f"donner une cle de securite"}
                    await websocket.send(json.dumps(response))
        except websockets.ConnectionClosed:
            logger.info(f"Connection closed during authentication for client: {client_addr}")
        except Exception as e:
            logger.error(f"Error in handler for client {client_addr}: {e}", exc_info=True)

    async def queue_consumer(self):
        '''
            Consumes messages from queue and sends to WebSocket clients
        '''
        loop = asyncio.get_event_loop()
        while not self.stop_event.is_set():
            try:
                # Non-blocking get with timeout
                msg = await loop.run_in_executor(None, self.message_queue.get, True, 0.1)
                await self._async_send_to_all_clients(msg)
            except:
                # Queue empty or timeout
                await asyncio.sleep(0.01)



def websocket_server_thread(server):
    '''
        Runs the WebSocket server in its own event loop
    '''
    logger.info("Starting WebSocket server thread")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_server():
        async with websockets.serve(server.handler, "0.0.0.0", 8765):
            logger.info("WebSocket server listening on 0.0.0.0:8765")
            # Start queue consumer
            consumer_task = asyncio.create_task(server.queue_consumer())
            logger.debug("Queue consumer task created")
            # Wait for stop event
            while not server.stop_event.is_set():
                await asyncio.sleep(0.1)
            logger.warning("Stop event triggered - shutting down WebSocket server")
            consumer_task.cancel()
            logger.debug("Queue consumer task cancelled")

    loop.run_until_complete(run_server())
    logger.info("WebSocket server thread ended")


def main():
    logger.info("=== Starting main application ===")

    # Start HTTP server in daemon thread
    logger.info("Starting HTTP server thread")
    t = threading.Thread(target=http_srv.start_server, daemon=True)
    t.start()

    # Create server instance
    logger.info("Creating Server instance with MovementControl")
    server = Server(MovementControl())

    # Start camera loop in daemon thread
    logger.info("Starting camera loop thread")
    camera_thread = threading.Thread(target=server.camera_loop, daemon=True)
    camera_thread.start()

    # Start battery monitoring in daemon thread
    logger.info("Starting battery monitoring thread")
    battery_thread = threading.Thread(target=server.batterie, daemon=True)
    battery_thread.start()

    # Start WebSocket server in its own thread (non-daemon to keep main alive)
    logger.info("Starting WebSocket server thread")
    ws_thread = threading.Thread(target=websocket_server_thread, args=(server,))
    ws_thread.start()

    # Wait for stop event
    logger.info("Main thread waiting for stop event...")
    server.stop_event.wait()
    logger.warning("Stop event received in main - initiating shutdown sequence")

    # Wait for WebSocket thread to finish
    logger.info("Waiting for WebSocket thread to finish (timeout: 5s)")
    ws_thread.join(timeout=5)
    logger.info("=== Application shutdown complete ===")


def special():
    main()

if __name__ == "__main__":
    print(">>> démarrage du script remake.py")
    main()
    print(">>> script remake.py terminé")
