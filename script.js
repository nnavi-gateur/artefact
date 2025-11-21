/************ CONSOLE *************/
const consoleDiv = document.getElementById("consoleContent");
function serverLog(msg) {
    const time = new Date().toLocaleTimeString();
    consoleDiv.textContent += `[${time}] ${msg}\n`;
    consoleDiv.scrollTop = consoleDiv.scrollHeight;
}

const fallbackImages = [
    "image/fallback1.jpg"
];

function getRandomFallbackImage() {
    const i = Math.floor(Math.random() * fallbackImages.length);
    return fallbackImages[i];
}

// Gestion plein écran caméra
const fullPage = document.querySelector('#fullpage');
const fullscreenOverlay = document.getElementById('fullscreenOverlay');
let autoFullScreen = false;

    

/************ WEBSOCKET *************/
const ws = new WebSocket("ws://robotpi-62.enst.fr:8765");
const batteryDisplay = document.getElementById("battery");
const cameraImg = document.getElementById("camera");
const status = document.getElementById("status");

ws.onopen = () => {
    status.textContent = "Connecté ";
    serverLog("Connexion établie");
};
ws.onclose = () => {
    status.textContent = "Déconnecté ";
    serverLog("Connexion fermée");
};
ws.onerror = () => {
    status.textContent = "Erreur ";
    serverLog("Erreur WebSocket");
};
ws.onmessage = event => {
    let data;
    try { data = JSON.parse(event.data); }
    catch { return serverLog("JSON invalide"); }

    if (data.type !== "camera_frame") {
        serverLog("Réception : " + event.data);
    }

    if (data.type === "battery")
        batteryDisplay.textContent = "Batterie: " + data.level + "%";

    if (data.type === "camera_frame"){
       if (data.frame) {
           cameraImg.src = "data:image/jpeg;base64," + data.frame;
       }else{
           const fallback = getRandomFallbackImage();
            cameraImg.src = fallback;
       }
    if (autoFullScreen) {
            fullPage.style.backgroundImage = `url(${cameraImg.src})`;
        }
    }

    if (data.type === "auto_started") {
        // Passage en mode plein écran caméra après confirmation serveur idée de ouf
        autoFullScreen = true;
        autoBtn.classList.add("auto-active");

        fullPage.style.display = "block";
        if (fullscreenOverlay) {
            fullscreenOverlay.style.display = "block";
        }
        if (cameraImg.src) {
            fullPage.style.backgroundImage = `url(${cameraImg.src})`;
        }
    }
};

/************ Buttons*************/
const stopBtn = document.getElementById("stopBtn");
const autoBtn = document.getElementById("autoBtn");
const connectBTN = document.getElementById("connectBTN");

stopBtn.onclick = () => {
    serverLog("Envoi: stop_server");
    ws.send(JSON.stringify({ type: "stop_server" }));
};

function parseInitPos(text) {
  text = text.trim();
  if (!text) return null;

  try {
    const obj = JSON.parse(text);
    if (typeof obj.x === "number" && typeof obj.y === "number") {
      return obj;
    }
  } catch {}

  const parts = text.split(",");
  if (parts.length >= 2) {
    const [x, y, theta] = parts.map(Number);
    if (!isNaN(x) && !isNaN(y))
      return { x, y, theta: theta || 0 };
  }
  return null;
}

autoBtn.onclick = () => {
    const text = document.getElementById("initPos").value;
    const error = document.getElementById("initPosError");
    const ok = document.getElementById("initPosOk");

    const parsed = parseInitPos(text);

    error.style.display = parsed ? "none" : "block";
    ok.style.display = parsed ? "block" : "none";

    const payload = { type: "start_auto" };
    if (parsed) payload.init_pos = parsed;

    serverLog("Envoi : " + JSON.stringify(payload));
    ws.send(JSON.stringify(payload));
};
connectBTN.onclick = () => {
    const text = document.getElementById("key").value;

    serverLog("Envoi clef" );
    ws.send(JSON.stringify({ type: "key",value:text}));
};

document.getElementById('closeFullscreen').onclick = () => {
    autoFullScreen = false;
    fullPage.style.display = "none";
    overlay.style.display = "none";
};


//gear mode
let mode = 1; 
const gearBtn = document.getElementById("gearBtn");
gearBtn.addEventListener("click", () => {
    mode = mode < 3 ? mode + 1 : 1;
    gearBtn.textContent = "Boîte de vitesse: " + mode;
    current.mode = mode; // mettre à jour le mode envoyé au serveur
});


/************ JOYSTICK *************/
const canvas = document.getElementById("joystick");
const ctx = canvas.getContext("2d");
const center = { x: 150, y: 150 };
const knobRadius = 40;
const maxRadius = 100;

let knob = { x: center.x, y: center.y };
let current = { 
    type: "command",
    angle: 0,
    distance: 0,
    mode: 1,
    x: 0,
    y: 0
};

let lastSent = { angle: null, distance: null, x: null, y: null };
let zeroCount = 0;

function drawJoystick() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.beginPath();
    ctx.arc(center.x, center.y, 150, 0, Math.PI * 2);
    ctx.fillStyle = "#80d5ff";
    ctx.fill();

    ctx.beginPath();
    ctx.arc(knob.x, knob.y, knobRadius, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(0,0,0,0.5)";
    ctx.fill();
}
drawJoystick();

const mc = new Hammer(canvas);
mc.get("pan").set({ direction: Hammer.DIRECTION_ALL });

mc.on("panmove", ev => {
    const dx = ev.deltaX;
    const dy = ev.deltaY;

    const distance = Math.min(Math.sqrt(dx*dx + dy*dy), maxRadius);
    const angle = (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360;

    // Position du knob
    knob.x = center.x + distance * Math.cos((angle - 90) * Math.PI/180);
    knob.y = center.y + distance * Math.sin((angle - 90) * Math.PI/180);

    current.angle = Math.round(angle);
    current.distance = Math.round(distance);

    // Coordonnées cartésiennes normalisées [-1 ; 1]
    current.x = Number((dx / maxRadius).toFixed(3));
    current.y = Number((dy / maxRadius).toFixed(3));

    drawJoystick();
});

mc.on("panend", () => {
    knob = { x: center.x, y: center.y };
    drawJoystick();

    current.angle = 0;
    current.distance = 0;
    current.x = 0;
    current.y = 0;
});

/************ ENVOI WS OPTIMISÉ *************/
setInterval(() => {
    if (ws.readyState !== WebSocket.OPEN) return;

    const isZero = current.angle === 0 && current.distance === 0;

    if (isZero) {
        zeroCount++;
        if (zeroCount >= 2) return;
    } else {
        zeroCount = 0;
    }

    // Envoi si changement angle/distance/X/Y
    if (
        current.angle !== lastSent.angle ||
        current.distance !== lastSent.distance ||
        current.x !== lastSent.x ||
        current.y !== lastSent.y
    ) {
        ws.send(JSON.stringify(current));

        lastSent.angle = current.angle;
        lastSent.distance = current.distance;
        lastSent.x = current.x;
        lastSent.y = current.y;
    }
}, 50);


