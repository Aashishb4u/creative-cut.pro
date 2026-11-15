// The landing page's 3D story, drawn with three.js and driven by scrolling.
// One long video floats under the headline. Scroll down and it plays, the AI marks the moments worth keeping,
// and those moments lift out as three vertical clips. Nothing here is needed to use the page: without WebGL,
// or with reduced motion asked for, the steps are shown as plain text instead.
import * as THREE from "/assets/three-r170.js";

const canvas = document.getElementById("stage3d");
const story = document.getElementById("story");
const steps = [...document.querySelectorAll(".story-steps li")];
const rail = document.querySelector(".story-rail i");
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;

function webglOK() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch { return false; }
}

if (canvas && story && webglOK()) start();

function start() {
  const renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true, powerPreference: "high-performance"});
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  document.documentElement.classList.add("has3d");

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
  const world = new THREE.Group();          // everything that tilts with the pointer
  scene.add(world);
  const stage = new THREE.Group();          // the video and its clips: moved aside so the steps never cover them
  world.add(stage);

  scene.add(new THREE.HemisphereLight(0xffffff, 0xf9d0d0, 1.5));
  const key = new THREE.DirectionalLight(0xffffff, 2.4); key.position.set(4, 6, 9); scene.add(key);
  const rim = new THREE.DirectionalLight(0xffd23f, 1.6); rim.position.set(-7, -2, 5); scene.add(rim);

  // ---------------------------------------------------------------- shapes and pictures
  function rounded(w, h, r) {
    const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
    s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
    s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
    s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
    return s;
  }
  function faceGeometry(shape, w, h) {
    const g = new THREE.ShapeGeometry(shape, 12), p = g.attributes.position, uv = g.attributes.uv;
    for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) / w + 0.5, p.getY(i) / h + 0.5);
    return g;
  }
  function paint(w, h, draw) {
    const c = document.createElement("canvas"); c.width = w; c.height = h;
    draw(c.getContext("2d"), w, h);
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
    return t;
  }
  function pill(g, x, y, w, h, r, fill) {
    g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
    g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); g.fillStyle = fill; g.fill();
  }
  function landscape(g, w, h, top, bottom, hill1, hill2) {
    const sky = g.createLinearGradient(0, 0, 0, h); sky.addColorStop(0, top); sky.addColorStop(1, bottom);
    g.fillStyle = sky; g.fillRect(0, 0, w, h);
    g.fillStyle = "rgba(255,255,255,.85)"; g.beginPath(); g.arc(w * 0.72, h * 0.3, h * 0.09, 0, 7); g.fill();
    g.fillStyle = hill1; g.beginPath(); g.moveTo(0, h * 0.78);
    g.bezierCurveTo(w * 0.25, h * 0.5, w * 0.45, h * 0.62, w * 0.6, h * 0.7); g.bezierCurveTo(w * 0.8, h * 0.8, w * 0.9, h * 0.6, w, h * 0.66);
    g.lineTo(w, h); g.lineTo(0, h); g.fill();
    g.fillStyle = hill2; g.beginPath(); g.moveTo(0, h * 0.9);
    g.bezierCurveTo(w * 0.3, h * 0.72, w * 0.6, h * 0.95, w, h * 0.8); g.lineTo(w, h); g.lineTo(0, h); g.fill();
  }
  // the long video: a 16:9 frame with a timeline and a waveform whose loud spots are the moments
  const LOUD = [0.17, 0.52, 0.81];
  const slabTex = paint(1280, 720, (g, w, h) => {
    landscape(g, w, h, "#FFF6C2", "#FFB8B8", "#E5202E", "#9E1020");
    g.fillStyle = "rgba(20,10,20,.55)"; g.fillRect(0, h * 0.8, w, h * 0.2);
    for (let i = 0; i < 120; i++) {
      const x = 40 + i * ((w - 80) / 120), near = Math.min(...LOUD.map(l => Math.abs(i / 120 - l)));
      const amp = near < 0.03 ? 0.75 + Math.random() * 0.25 : 0.12 + Math.random() * 0.3;
      g.fillStyle = near < 0.03 ? "#FFD84D" : "rgba(255,255,255,.75)";
      const bh = amp * h * 0.11; g.fillRect(x, h * 0.9 - bh / 2, 5, bh);
    }
    pill(g, 40, h * 0.06, 230, 44, 22, "rgba(255,255,255,.92)");
    g.fillStyle = "#E5323F"; g.beginPath(); g.arc(70, h * 0.06 + 22, 8, 0, 7); g.fill();
    g.fillStyle = "#15110F"; g.font = "600 24px Montserrat, Arial, sans-serif"; g.fillText("3:42:10 long", 90, h * 0.06 + 31);
  });
  // a finished clip: vertical, with a hook at the top and word-by-word captions
  const CLIP_LOOKS = [["#FFD23F", "#FF7A1F", "#E5202E", "#9E1020"], ["#F3FFD6", "#B8FF3D", "#3F8F2A", "#1F3D0C"], ["#F9D0D0", "#FF5A5F", "#5C0F14", "#15110F"]];
  const HOOKS = ["WAIT FOR IT", "HE SAID WHAT", "NOBODY SAW THIS"];
  const clipTex = CLIP_LOOKS.map((c, i) => paint(540, 960, (g, w, h) => {
    landscape(g, w, h, c[0], c[1], c[2], c[3]);
    g.font = "800 46px Montserrat, Arial, sans-serif"; const hw = g.measureText(HOOKS[i]).width + 56;
    pill(g, (w - hw) / 2, h * 0.12, hw, 78, 18, "#fff");
    g.fillStyle = "#15110F"; g.textAlign = "center"; g.fillText(HOOKS[i], w / 2, h * 0.12 + 55);
    g.font = "900 58px Montserrat, Arial, sans-serif"; g.lineWidth = 12; g.strokeStyle = "#15110F";
    const words = [["THIS", "#fff"], ["CHANGES", "#FFD84D"]];
    words.forEach(([t, col], k) => { const y = h * 0.66 + k * 70; g.strokeText(t, w / 2, y); g.fillStyle = col; g.fillText(t, w / 2, y); });
    pill(g, 40, h - 46, w - 80, 8, 4, "rgba(255,255,255,.35)"); pill(g, 40, h - 46, (w - 80) * (0.3 + i * 0.2), 8, 4, "#fff");
  }));

  const blue = new THREE.MeshStandardMaterial({color: 0xe5202e, metalness: 0.15, roughness: 0.32});
  function slabMesh(w, h, r, depth, tex) {
    const group = new THREE.Group(), shape = rounded(w, h, r);
    const body = new THREE.Mesh(new THREE.ExtrudeGeometry(shape, {depth, bevelEnabled: true, bevelThickness: 0.035, bevelSize: 0.035, bevelSegments: 3, curveSegments: 12}), blue);
    body.position.z = -depth / 2; group.add(body);
    const face = new THREE.Mesh(faceGeometry(shape, w, h), new THREE.MeshBasicMaterial({map: tex, toneMapped: false, transparent: true}));
    face.position.z = depth / 2 + 0.04; face.renderOrder = 1; group.add(face);
    group.userData.face = face;
    return group;
  }

  // ---------------------------------------------------------------- the pieces
  const SW = 6.4, SH = 3.6;
  const slab = slabMesh(SW, SH, 0.24, 0.14, slabTex);
  stage.add(slab);
  const glowMat = () => new THREE.MeshBasicMaterial({color: 0xff5a5f, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false});
  const playhead = new THREE.Mesh(new THREE.PlaneGeometry(0.035, SH * 0.98), new THREE.MeshBasicMaterial({color: 0xffffff, transparent: true, opacity: 0.95, toneMapped: false, depthWrite: false}));
  playhead.position.z = 0.13; playhead.renderOrder = 3; slab.add(playhead);
  const SEG_W = 1.15, segX = LOUD.map(l => (l - 0.5) * SW);
  const marks = segX.map(x => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(SEG_W, SH * 0.98), glowMat());
    m.position.set(x, 0, 0.12); m.renderOrder = 2; slab.add(m);
    const edges = [-1, 1].map(s => { const e = new THREE.Mesh(new THREE.PlaneGeometry(0.03, SH * 1.06), new THREE.MeshBasicMaterial({color: 0xffffff, transparent: true, opacity: 0, toneMapped: false, depthWrite: false}));
      e.position.set(x + s * SEG_W / 2, 0, 0.14); e.renderOrder = 3; slab.add(e); return e; });
    return {m, edges};
  });

  const CW = 1.35, CH = 2.4;
  const clips = clipTex.map(t => { const c = slabMesh(CW, CH, 0.17, 0.1, t); c.scale.setScalar(0.001); stage.add(c); return c; });

  // sparkles and two glossy orbs, as in the brand sheet
  const starTex = paint(64, 64, (g, w) => {
    const r = w / 2; g.translate(r, r); g.fillStyle = "#fff"; g.beginPath();
    for (let i = 0; i < 4; i++) { g.rotate(Math.PI / 2); g.quadraticCurveTo(r * 0.12, r * 0.12, 0, r); g.quadraticCurveTo(-r * 0.12, r * 0.12, 0, 0); }
    g.fill();
  });
  const N = 140, pos = new Float32Array(N * 3), seed = new Float32Array(N);
  for (let i = 0; i < N; i++) { pos[i * 3] = (Math.random() - 0.5) * 16; pos[i * 3 + 1] = (Math.random() - 0.5) * 9; pos[i * 3 + 2] = (Math.random() - 0.5) * 6 - 1; seed[i] = Math.random() * 6.28; }
  const sparkGeo = new THREE.BufferGeometry(); sparkGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const sparks = new THREE.Points(sparkGeo, new THREE.PointsMaterial({color: 0xffd23f, size: 0.16, map: starTex, transparent: true, opacity: 0.85, depthWrite: false, alphaTest: 0.01}));
  world.add(sparks);
  const orbMat = new THREE.MeshStandardMaterial({color: 0xff5a5f, metalness: 0.1, roughness: 0.15, emissive: 0xe5202e, emissiveIntensity: 0.35});
  const orbs = [[-4.2, 1.6, -1, 0.42], [4.4, -1.4, -0.5, 0.3]].map(([x, y, z, r]) => { const o = new THREE.Mesh(new THREE.SphereGeometry(r, 48, 32), orbMat); o.position.set(x, y, z); o.userData.base = [x, y, z]; world.add(o); return o; });

  // ---------------------------------------------------------------- sizing
  let W = 0, H = 0, narrow = false, off = 0, sc = 1, lift = 0, low = -2.15;
  const list = document.querySelector(".story-steps");
  function layout() {
    // where the scene sits once the steps are on screen: beside them on a wide screen, above them on a narrow one
    const visH = 2 * camera.position.z * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)), visW = visH * camera.aspect;
    low = -visH * 0.36;                      // under the headline: only the top of the video shows at first
    if (W >= 1100 && list) {
      const left = (list.getBoundingClientRect().right / W - 0.5) * visW + 0.35, right = visW / 2 - 0.25;
      sc = Math.min(1, (right - left) / (SW * 1.04)); off = (left + right) / 2; lift = 0;
    } else { off = 0; sc = 1; lift = visH * 0.11; }
  }
  function resize() {
    W = innerWidth; H = innerHeight; narrow = W < 760;
    renderer.setSize(W, H, false);
    camera.aspect = W / H;
    const fit = (SW * 0.62) / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) / camera.aspect;   // keep the long video on screen
    camera.position.set(0, 0, Math.max(11, fit));
    camera.updateProjectionMatrix();
    layout();
    dirty = true;
  }

  // ---------------------------------------------------------------- scroll to scene
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const ease = t => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  const back = t => { const c = 1.6; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); };
  const span = (p, a, b) => clamp((p - a) / (b - a));
  const lerp = (a, b, t) => a + (b - a) * t;
  let intro = 0, prog = 0, visible = true;
  function readScroll() {
    const r = story.getBoundingClientRect();
    intro = clamp(1 - r.top / H);                                   // the story's top climbing from the bottom of the screen
    prog = clamp(-r.top / Math.max(1, r.height - H));               // 0 to 1 while it is pinned
    visible = r.bottom > 0;
    canvas.style.opacity = String(clamp(r.bottom / (H * 0.6)));
    const active = prog < 0.34 ? 0 : prog < 0.62 ? 1 : 2;
    steps.forEach((s, i) => s.classList.toggle("on", i === active && intro > 0.6));
    if (rail) rail.style.transform = `scaleY(${prog})`;
    dirty = true;
  }

  const finals = () => narrow ? [[-1.6, 0.5, 1.6, 0.26], [0, 0.8, 2.1, 0], [1.6, 0.5, 1.6, -0.26]]
                              : [[-2.0, 0.15, 1.8, 0.28], [0, 0.35, 2.3, 0], [2.0, 0.15, 1.8, -0.28]];
  let mx = 0, my = 0, tx = 0, ty = 0, dirty = true;
  addEventListener("pointermove", e => { tx = (e.clientX / W - 0.5) * 2; ty = (e.clientY / H - 0.5) * 2; }, {passive: true});

  function frame(time) {
    const t = still ? 0 : time / 1000;
    mx = lerp(mx, still ? 0 : tx, 0.05); my = lerp(my, still ? 0 : ty, 0.05);
    world.rotation.y = mx * 0.12; world.rotation.x = my * 0.06;

    // in: the long video rises from under the headline and turns to face you
    const i = ease(intro);
    const a = span(prog, 0, 0.34), b = span(prog, 0.3, 0.62), c = span(prog, 0.6, 0.95);
    const away = ease(c);
    stage.position.set(lerp(0, off, i), lerp(0, lift, i), 0);
    stage.scale.setScalar(lerp(1, sc, i));
    slab.position.set(0, lerp(lerp(low, 0.25, i), -0.9, away) + Math.sin(t * 0.8) * 0.05, lerp(0, -2.6, away));
    slab.rotation.set(lerp(-0.42, -0.06, i) + away * 0.18, lerp(0.38, 0, i) + Math.sin(t * 0.4) * 0.03, 0);
    slab.scale.setScalar(lerp(0.86, 1, i) * lerp(1, 0.78, away));

    // 1: it plays
    playhead.position.x = lerp(-SW / 2 + 0.1, SW / 2 - 0.1, a < 1 ? a : (t * 0.15) % 1);
    playhead.material.opacity = 0.95 * (1 - away);
    // 2: the loud, catchy moments light up and get cut lines, one after another
    marks.forEach((k, n) => {
      const on = span(b, n * 0.22, n * 0.22 + 0.45);
      k.m.material.opacity = on * 0.42 * (1 - away * 0.6) * (0.85 + Math.sin(t * 3 + n) * 0.15);
      k.m.visible = on > 0.001;
      k.edges.forEach(e => { e.material.opacity = on; e.visible = on > 0.001; });
    });
    // 3: those moments lift out as vertical clips
    const F = finals();
    clips.forEach((cl, n) => {
      const p = span(c, n * 0.12, n * 0.12 + 0.62), q = back(p), f = F[n];
      const from = new THREE.Vector3(segX[n], slab.position.y, slab.position.z + 0.3);
      cl.position.set(lerp(from.x, f[0], ease(p)), lerp(from.y, f[1], ease(p)) + (p > 0.99 ? Math.sin(t * 1.1 + n) * 0.06 : 0), lerp(from.z, f[2], ease(p)));
      cl.rotation.set(0, lerp(0, f[3], ease(p)) + (1 - p) * 0.6, (1 - p) * (n - 1) * 0.3);
      cl.scale.setScalar(Math.max(0.001, q * (narrow ? 1.15 : 1)));
      cl.visible = p > 0.001;
    });

    orbs.forEach((o, n) => { const [x, y, z] = o.userData.base; o.position.set(x + Math.sin(t * 0.5 + n) * 0.15, y + Math.sin(t * 0.7 + n * 2) * 0.2, z); o.scale.setScalar(Math.max(0.001, 1 - i)); o.visible = !narrow && i < 0.98; });   // they decorate the headline only
    sparks.rotation.y = t * 0.02; sparks.material.opacity = 0.55 + 0.3 * Math.sin(t * 1.3);

    renderer.render(scene, camera);
    dirty = false;
  }

  let raf = 0;
  function loop(time) {
    raf = 0;
    if (visible && !document.hidden) frame(time);
    if ((!still && visible && !document.hidden) || dirty) raf = requestAnimationFrame(loop);   // idle once scrolled past
  }
  const kick = () => { if (!raf) raf = requestAnimationFrame(loop); };
  addEventListener("scroll", () => { readScroll(); kick(); }, {passive: true});
  addEventListener("resize", () => { resize(); readScroll(); kick(); });
  document.addEventListener("visibilitychange", kick);
  resize(); readScroll(); kick();
}
