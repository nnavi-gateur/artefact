from math import atan2, floor, pi, dist, cos, sin, copysign, radians
import beacon_detection.camera_Api as camera
from functools import partial
import requests
import threading
import time
import logging

from movement_control.positioning_system import TargetDistance

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)

addrCompl = "/api"
InnerRadius = 80
pos1 = (0, 150)
pos2 = (150, 0)
pos3 = (0, -150)

def deg_to_rad(d):
    '''
    transforme un degré en radiant

    arg : d = int
    '''
    return d * pi / 180



class AutoProgramme:
    def __init__(self,robot,position):
        logger.info("Initializing AutoProgramme")
        self.capture = 0
        self.run =False
        self.position = position
        self.robot = robot
        self.stop_rotation_event = threading.Event()
        self.latest_frame = None
        self.stop_rotation = threading.Event()
        logger.debug(f"AutoProgramme initialized - capture: {self.capture}, run: {self.run}")



    def update_pos(self):
        '''

        Fait tourner le robot jusqu'à avoir 3 Balises fixe (entre 1 et 4) dans le champ

        '''
        # Wait for camera to be ready
        logger.info("Starting position update - waiting for camera to be ready")

        while self.latest_frame is None:
            logger.debug("Waiting for camera frame...")
            time.sleep(0.05)
        logger.info("Camera ready - starting beacon detection rotation")

        self.stop_rotation_event.clear()
        # rotate_thread = threading.Thread(target=self.rotate_robot_c_times,args=[18], daemon=True)
        # rotate_thread.start()
        logger.debug("Rotation thread started (18 iterations)")

        # markers = camera.detect_markers(self.latest_frame)
        dispo = []
        viewed = []
        last_angle = 0
        # dispo = [TargetDistance(m['id'],m['distance']*10,m['id']==1) for m in markers if 0 < m['id'] < 5] if markers else []
        # viewed = [m['id'] for m in markers if 0 < m['id'] < 5]
        logger.info(f"Initial markers detected: {len(dispo)}, IDs: {viewed}")

        for i in range(18):
            for k in range (10):
                markers = camera.detect_markers(self.latest_frame)
                # print (markers)
                for m in markers :
                    if not m['id'] in viewed and 0 < m['id'] < 5 :
                        logger.debug(f"New beacon found - ID: {m['id']}, distance: {m['distance']*10}")
                        dispo.append(TargetDistance(m['id'],m['distance']*10,False))
                        viewed.append(m['id'])
                        last_angle = m['horizontal_angle']
                time.sleep(0.10)
            if len(dispo) < 3:
                if self.robot is not None:
                    self.robot.turn_precise(deg_to_rad(20))
            else:
                break

            # markers = camera.detect_markers(self.latest_frame)
            # for m in markers :
            #     if not m['id'] in viewed and 0 < m['id'] < 5 :
            #         logger.debug(f"New beacon found - ID: {m['id']}, distance: {m['distance']*10}")
            #         dispo.append(TargetDistance(m['id'],m['distance']*10,m['id']==1))
            #         viewed.append(m['id'])
            # if index % 50 ==0:
            #     logger.debug(f"Still searching for beacons - iteration: {index}, found: {len(dispo)}/3")

        # self.stop_rotation_event.set()
        # rotate_thread.join(timeout=0.1)
        logger.info(f"Found 3 beacons - stopping rotation. Beacons: {[d.id for d in dispo]}")

        # Center on the last beacon located (should be beacon 1)
        angle = last_angle
        
        if self.robot is not None:
            self.robot.turn_precise(-deg_to_rad(angle))

        dispo[-1].facing = True

        logger.info("Calculating new position based on detected beacons")
        self.position.find_target(dispo)
        logger.info("Position updated successfully")
        x, y, theta = self.position.get_position()
        logger.debug(f"New position - x: {x:.2f}, y: {y:.2f}, theta: {theta:.2f}")
        time.sleep(1)

        return 

    def camera_loop(self):

        '''

        Envoie la caméra toutes les x frames

        '''
        logger.info("Camera loop started for AutoProgramme")
        frame_count = 0
        while self.run:
            frame = camera.get_camera_frame()
            if frame is not None:
                self.latest_frame = frame
                frame_count += 1
            time.sleep(0.02)
        logger.info(f"Camera loop stopped - total frames: {frame_count}")

    def rotate_robot_continuously(self):

        '''

            fait tourner la caméra par accoup de 4 degrés jusq'à son arret

            arg speed : int
                duration : int
                step : int

        '''

        while not self.stop_rotation.is_set():
            time.sleep(2)
            if self.robot is not None:
                t = 0
                self.robot.turn_precise(deg_to_rad(20))
    def rotate_robot_c_times(self,c):

        '''

            fait tourner la caméra par accoup de 4 degrés jusq'à son arret

            arg speed : int
                duration : int
                step : int

        '''

        for i in range (c):

            if self.stop_rotation_event.is_set():
                return
            time.sleep(2)
            if self.robot is not None:
                t = 0
                self.robot.turn_precise(deg_to_rad(20))

    def locate_balise(self,k):

        '''
        Recherche la balise k en regardant autour de lui

        arg : k = int
        timeout =int

        output : Dictionary ( 'id' : int, ' distance' : int, 'angle': int)

        '''
        logger.info(f"Starting search for beacon ID: {k}")
        while self.latest_frame is None:
            logger.debug("Waiting for camera frame...")
            time.sleep(0.05)
            logger.info("Camera ready - starting beacon detection rotation")
        dispo =None


        for i in range(18):
            for j in range (10):
                markers = camera.detect_markers(self.latest_frame)
                # print(markers)
                for m in markers :
                    if m['id'] ==k :
                        logger.debug(f"Balise found - ID: {m['id']}, distance: {m['distance']*10}")
                        dispo = m
                time.sleep(0.10)
            if dispo == None:
                if self.robot is not None:
                        self.robot.turn_precise(deg_to_rad(20))
            else:
                break

        if dispo != None:
            logger.info(f"Found balise {k}")

        # Center on the last beacon located (should be beacon 1)
            angle = dispo['horizontal_angle']
            if self.robot is not None:
                self.robot.turn_precise(-deg_to_rad(angle))


        return dispo

    def locate_balise_next(self):
        '''

        Recherche la prochaine balise dans son champs de vision qui n'est pas dans [|1,4|] en regardant autour de lui

        arg :
        timeout =int

        output : Dictionary

        '''
        logger.info(f"Starting search for next beacon ")
        while self.latest_frame is None:
            logger.debug("Waiting for camera frame...")
            time.sleep(0.05)
            logger.info("Camera ready - starting beacon detection rotation")
        dispo =None
        for i in range(18):
            for j in range (10):
                markers = camera.detect_markers(self.latest_frame)
                # print(markers)
                for m in markers :
                    if m['id'] not in {0,1,2,3,4} :
                        logger.debug(f"Balise found - ID: {m['id']}, distance: {m['distance']*10}")
                        dispo = m
                time.sleep(0.10)
            if dispo == None:
                if self.robot is not None:
                        self.robot.turn_precise(deg_to_rad(20))
            else:
                break

        if dispo != None:
            logger.info(f"Found balise next")

        # Center on the last beacon located (should be beacon 1)
            angle = dispo['horizontal_angle']
            if self.robot is not None:
                self.robot.turn_precise(-deg_to_rad(angle))


        return dispo 


    def send_position_periodic(self):
        '''

        Envoie la position au serveur d'éval toutes les secondes

        '''
        global addrCompl
        logger.info("Starting periodic position reporting to evaluation server")
        send_count = 0
        while self.run:
            x,y,theta = self.position.get_position()
            x = x/10
            y = y/10

            url = f"http://proj103.r2.enst.fr{addrCompl}/pos?x={x}&y={y}"
            # print(x,y)
            send_count += 1
            try:
                response = requests.post(url, timeout=5)
                if send_count % 10 == 0:
                    logger.debug(f"Position send status: {response.status_code}")
            except Exception as e:
                logger.error(f"Failed to send position to server: {e}")
            time.sleep(1.0)
        logger.info(f"Stopped periodic position reporting - total sends: {send_count}")

    def watcher(self,send_callback):

        '''

        Arrête le programe lorsque le nombre de drapeaux capturés est de 2

        arg : send_callback = function

        '''
        logger.info(f"Watcher started - waiting for 2 captures (current: {self.capture})")

        while self.capture < 2:
            time.sleep(0.1)
        logger.info(f"Target reached - {self.capture} beacons captured, stopping program")
        self.run = False
        send_callback({"type": "finished", "msg": "Course complete"})

    def valide_balise(self,balise,send_callback):
        '''

        A partir des info d'une balise trouvée par ka caméra,
        effectue le calcul de sa position, s'en rapproche et le renvoie au serveur


        arg : send_callback = function

        '''
        if balise:
            beacon_id = balise["id"]
            beacon_distance = balise["distance"]
            logger.info(f"Validating beacon - ID: {beacon_id}, distance: {beacon_distance}")
            send_callback({
                "type": "found",
                "msg": "balise trouvee a une distance",
                "distance": beacon_distance
            })

            x,y,theta = self.position.get_position()
            x=x/10
            y=y/10
            logger.debug(f"Robot position before approach - x: {x:.2f}, y: {y:.2f}, theta: {theta:.2f}")
            xbal = x+ beacon_distance*cos(theta)
            ybal = y+ beacon_distance*sin(theta)
            logger.debug(f"Calculated beacon position - x: {xbal:.2f}, y: {ybal:.2f}")
            #Oriente le robot vers le centre de la balise

            move_distance = beacon_distance * 10 - 200
            logger.info(f"Moving toward beacon - distance: {move_distance}")
            self.robot.move_precise(move_distance)

            '''  trouver l'orientation'''
            theta = atan2(ybal, xbal)
            theta_clock = (pi/2 - theta) % (2*pi) 
            sector_index = int(theta_clock // (pi/4)) 
            sector_index = (sector_index + 1) % 8
            sector = chr(65 + sector_index) 
            isInside = ( dist ((0 , 0) , ( xbal , ybal ) ) <=InnerRadius )
            logger.info(f"Beacon validation - ID: {beacon_id}, sector: {sector}, inside: {isInside}, position: ({x:.2f}, {y:.2f})")

            try:
                url = f"http://proj103.r2.enst.fr{addrCompl}/marker?id={beacon_id}&sector={sector}&inner={1 if isInside else 0}"
                logger.debug(f"Sending validation request: {url}")
                a = requests.post(url, timeout=10)
                logger.info(f"Validation response - status: {a.status_code}")

                if a.status_code==200:
                    self.capture +=1
                    logger.info(f"Beacon {beacon_id} VALIDATED - total captures: {self.capture}/2")
                    self.robot.turn_precise(deg_to_rad(180))
                    self.robot.turn_precise(deg_to_rad(180))
                elif a.status_code==503:
                    self.capture +=1
                    self.robot.turn_precise(deg_to_rad(180))
                    self.robot.turn_precise(deg_to_rad(180))
                    logger.info(f"Beacon {beacon_id} VALIDATED OUT OF COURSE - total captures: {self.capture}/2")
                else :
                    logger.error(f"Beacon {beacon_id} VALIDATION FAILED - status: {a.status_code}, response: {a.text}")
            except Exception as e:
                logger.error(f"Error during beacon validation API call: {e}", exc_info=True)
        else:
            logger.warning("Beacon validation called with None/empty beacon")
            send_callback({"type": "not_found", "msg": "balise non trouvée"})


    def active(self,send_callback):

        '''

        Effectue le travail automatique :
        - recherche le premier drapeau à capturer  ( au centre)
        - Va se placer proche du drapeau et récupère sa position exacte à l'aide des balises de contrôle
        - Renvoie la zone du drapeau
        - Si c'est correcte, cherche le prochain drapeau à capturer
        - va s'approcher de ce nouveau drapeau


        arg : send_callback = function

        '''

        logger.info("=== Starting automatic beacon capture sequence ===")

        logger.info("Initial movement - advancing 1500 units")
        self.robot.move_precise(1300)

        logger.info("Updating position using beacon triangulation")
        self.update_pos()

        logger.info("Locating first target beacon (not in [1-4])")
        m = self.locate_balise_next() # récupère la balise centrale

        if m is None:
            logger.error("First target beacon not found - aborting")
            return

        first_id = m["id"]
        logger.info(f"First target beacon located - ID: {first_id}")

        logger.info(f"Attempting to validate first beacon (ID: {first_id})")
        self.valide_balise(m,send_callback)
        
        #regarde si le serveur de test valide la prise de balise
        logger.info("Checking validation status with server")
        try:
            valide = requests.get(f"http://proj103.r2.enst.fr{addrCompl}/status", timeout=10).json()
            absent = not any(m["id"] == first_id for m in valide["markers"])
            if absent :
                logger.error(f"FIRST BEACON VALIDATION REJECTED BY SERVER - ID: {first_id}")
                # return
            else :
                logger.info(f"First beacon validated by server - proceeding to second beacon")
        except Exception as e:
            logger.error(f"Failed to check validation status: {e}")
            # return

        logger.info("Fetching list of remaining beacons to capture")
        try:
            todo = requests.get(f"http://proj103.r2.enst.fr{addrCompl}/list", timeout=10).json()
            next_id = todo["markers"][0]
            logger.info(f"Next beacon to capture - ID: {next_id}")
            m = self.locate_balise(next_id)

            logger.info(f"Attempting to validate second beacon (ID: {next_id})")
            self.valide_balise(m,send_callback)
            logger.info("=== Automatic beacon capture sequence complete ===")
        except Exception as e:
            logger.error(f"Failed to get next beacon or validate: {e}", exc_info=True)
        self.go_to(0,0)


    def go_to(self, x_target, y_target):
        """
        Déplace le robot vers une position cible (x_target, y_target) en mm
        
        Args:
            x_target (float): Coordonnée X cible en mm
            y_target (float): Coordonnée Y cible en mm
        """
        if self.robot is None or self.position is None:
            logger.error("Robot ou système de positionnement non initialisé")
            return

        # Récupère la position actuelle
        x_current, y_current, theta_current = self.position.get_position()
        logger.info(f"Current position - x: {x_current:.2f} mm, y: {y_current:.2f} mm, theta: {theta_current:.2f} rad")

        # Calcule la distance et l'angle vers la cible
        dx = x_target - x_current
        dy = y_target - y_current
        distance_to_target = dist((0, 0), (dx, dy))  # déjà en mm
        angle_to_target = atan2(dy, dx)

        # Calcule l'angle relatif à l'orientation actuelle du robot
        relative_angle = angle_to_target - theta_current
        # Normalise entre -pi et pi
        relative_angle = (relative_angle + pi) % (2 * pi) - pi

        logger.info(f"Moving to target - x: {x_target:.2f} mm, y: {y_target:.2f} mm")
        logger.debug(f"Computed relative angle: {relative_angle:.2f} rad, distance: {distance_to_target:.2f} mm")

        # Tourne le robot vers la cible
        self.robot.turn_precise(relative_angle)

        # Avance vers la cible
        self.robot.move_precise(distance_to_target)

        # Met à jour la position interne
        self.position.set_position(x_target, y_target, angle_to_target)
        logger.info(f"Arrived at target - x: {x_target:.2f} mm, y: {y_target:.2f} mm, theta: {angle_to_target:.2f} rad")



def run_second_algo(send_callback, x1, y1, rbt):
    logger.info(f"=== run_second_algo STARTED === Initial position: x={x1}, y={y1}")
    alt = AutoProgramme(rbt,rbt.get_positioning_system())

    logger.info(f"Setting initial robot position - x: {x1}, y: {y1}, theta: 0")
    alt.position.set_position(x1,y1,0)
    alt.run = True

    # Start camera loop thread
    logger.info("Starting camera loop thread for auto mode")
    camera_thread = threading.Thread(target=alt.camera_loop, daemon=True)
    camera_thread.start()

    # Start position periodic thread
    logger.info("Starting periodic position reporting thread")
    position_thread = threading.Thread(target=alt.send_position_periodic, daemon=True)
    position_thread.start()

    # Start watcher thread
    # logger.info("Starting watcher thread (monitors capture count)")
    # watcher_thread = threading.Thread(target=alt.watcher, args=(send_callback,), daemon=True)
    # watcher_thread.start()

    # Run active in current thread
    logger.info("Executing main automatic sequence (active method)")
    try:
        alt.active(send_callback)
        logger.info("=== run_second_algo COMPLETED SUCCESSFULLY ===")
    except Exception as e:
        logger.error(f"=== run_second_algo FAILED === Error: {e}", exc_info=True)
        alt.run = False
    