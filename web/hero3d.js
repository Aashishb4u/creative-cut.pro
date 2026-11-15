// The hero's 3D stage: three finished clips float in a carousel. Drag them, hover to lift one, click a side
// clip to bring it forward. Without a pointer they turn slowly on their own. Nothing here is needed to read the
// page: with reduced motion asked for, the stage is drawn once and stays still.
import * as THREE from "/assets/three-r170.js";

const canvas = document.getElementById("hero3d");
if (canvas && canvas.parentElement) start();

function start() {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true, powerPreference: "high-performance"});
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
  camera.position.set(0, 0.25, 11.5);

  scene.add(new THREE.AmbientLight(0xffffff, 1.25));
  const key = new THREE.DirectionalLight(0xffffff, 1.9); key.position.set(3, 5, 7); scene.add(key);
  const rim = new THREE.PointLight(0xe8175d, 22, 22); rim.position.set(-5, 1.5, 5); scene.add(rim);
  const gold = new THREE.PointLight(0xffd23f, 10, 18); gold.position.set(5, -2, 4); scene.add(gold);

  // ---- the clips: each is a finished vertical clip drawn on a canvas, with a hook, a score and captions
  const CLIPS = [
    {src: "/clips/demo_clip_1.mp4", bg: ["#FFD23F", "#FF7A1F", "#E8175D"], hook: "WAIT FOR IT", score: 94, words: ["THIS", "CHANGES"]},
    {src: "/clips/demo_clips_2.mp4", bg: ["#FF5A7A", "#E8175D", "#3D1466"], hook: "HE SAID WHAT", score: 91, words: ["NOBODY", "EXPECTED"]},
    {src: "/clips/demo_clip_3.mp4", bg: ["#7A2BD0", "#E8175D", "#15110F"], hook: "NOBODY SAW THIS", score: 88, words: ["THE", "FINISH"]}
  ];
  const W = 540, H = 960, R = 56;

  function roundRect(g, x, y, w, h, r) {
    g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
    g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
  }
  function drawClip(c) {
    const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
    const g = cv.getContext("2d");
    g.clearRect(0, 0, W, H);
    roundRect(g, 0, 0, W, H, R); g.save(); g.clip();
    const sky = g.createLinearGradient(0, 0, 0, H);
    sky.addColorStop(0, c.bg[0]); sky.addColorStop(0.6, c.bg[1]); sky.addColorStop(1, c.bg[2]);
    g.fillStyle = sky; g.fillRect(0, 0, W, H);
    // a sun and a wave: the picture of the clip, drawn so it reads as footage placeholder art
    g.fillStyle = "rgba(255,255,255,.55)"; g.beginPath(); g.arc(W * 0.7, H * 0.38, 62, 0, 7); g.fill();
    g.fillStyle = "rgba(20,10,20,.55)"; g.beginPath(); g.moveTo(0, H * 0.72);
    g.bezierCurveTo(W * 0.3, H * 0.6, W * 0.55, H * 0.82, W, H * 0.66); g.lineTo(W, H); g.lineTo(0, H); g.fill();
    // hook pill
    g.font = "400 46px 'Archivo Black', Montserrat, sans-serif";
    const hw = g.measureText(c.hook).width + 60;
    roundRect(g, (W - hw) / 2, H * 0.1, hw, 88, 22); g.fillStyle = "#FFFFFF"; g.fill();
    g.fillStyle = "#15110F"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(c.hook, W / 2, H * 0.1 + 46);
    // captions, the second word highlighted
    g.font = "400 84px 'Archivo Black', Montserrat, sans-serif"; g.lineWidth = 14; g.strokeStyle = "#15110F";
    c.words.forEach((w, k) => {
      const y = H * 0.8 + k * 88;
      g.strokeText(w, W / 2, y); g.fillStyle = k === 1 ? "#FFD23F" : "#FFFFFF"; g.fillText(w, W / 2, y);
    });
    // score badge
    roundRect(g, 26, 26, 150, 60, 30); g.fillStyle = "rgba(20,10,20,.8)"; g.fill();
    g.font = "700 26px Montserrat, sans-serif"; g.fillStyle = "#FFFFFF"; g.textAlign = "center";
    g.fillText("SCORE " + c.score, 101, 57);
    // progress
    roundRect(g, 60, H - 60, W - 120, 10, 5); g.fillStyle = "rgba(255,255,255,.3)"; g.fill();
    roundRect(g, 60, H - 60, (W - 120) * 0.42, 10, 5); g.fillStyle = "#FFFFFF"; g.fill();
    g.restore();
    const t = new THREE.CanvasTexture(cv);
    t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
    return t;
  }

  const CW = 2.3, CH = CW * (H / W);
  const faceGeo = new THREE.PlaneGeometry(CW, CH);
  const backGeo = new THREE.PlaneGeometry(CW + 0.1, CH + 0.1);
  const backMat = new THREE.MeshBasicMaterial({color: 0x15110f});
  const cards = [];
  const carousel = new THREE.Group();
  scene.add(carousel);

  // a soft red halo behind the clips, so the stage has depth and the front clip reads as the hero
  const haloCv = document.createElement("canvas"); haloCv.width = haloCv.height = 512;
  const hg = haloCv.getContext("2d"), grd = hg.createRadialGradient(256, 256, 0, 256, 256, 256);
  grd.addColorStop(0, "rgba(232,23,93,.55)"); grd.addColorStop(0.45, "rgba(232,23,93,.18)"); grd.addColorStop(1, "rgba(232,23,93,0)");
  hg.fillStyle = grd; hg.fillRect(0, 0, 512, 512);
  const halo = new THREE.Mesh(new THREE.PlaneGeometry(12, 9), new THREE.MeshBasicMaterial({map: new THREE.CanvasTexture(haloCv), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.9}));
  halo.position.set(0, 0, -4.5);
  scene.add(halo);

  // a card keeps the shape of its video (portrait, square or landscape), fitted inside the card box
  function fit(a) { let w = CW, h = CW / a; if (h > CH) { h = CH; w = CH * a; } return [w, h]; }
  const videos = [];
  function build() {
    CLIPS.forEach((c, i) => {
      const group = new THREE.Group();
      const face = new THREE.Mesh(faceGeo, new THREE.MeshStandardMaterial({map: drawClip(c), transparent: true, roughness: 0.42, metalness: 0.02, emissive: 0xe8175d, emissiveIntensity: 0}));
      const back = new THREE.Mesh(backGeo, backMat);
      back.position.z = -0.02;
      group.add(back, face);
      group.userData = {i, face, back, glow: 0};
      carousel.add(group);
      cards.push(group);
      if (c.src) loadVideo(c, group);
    });
    renderOnce();
  }
  function loadVideo(c, group) {
    const v = document.createElement("video");
    Object.assign(v, {muted: true, loop: true, playsInline: true, preload: "auto", src: c.src});
    v.setAttribute("muted", ""); v.setAttribute("playsinline", "");
    v.addEventListener("loadedmetadata", () => {
      const [w, h] = fit(v.videoWidth / v.videoHeight);
      group.userData.face.geometry = new THREE.PlaneGeometry(w, h);
      group.userData.back.geometry = new THREE.PlaneGeometry(w + 0.1, h + 0.1);
      if (reduce) v.currentTime = 0.6;                              // reduced motion: one still frame, no playing
    });
    v.addEventListener("loadeddata", () => {
      const tex = new THREE.VideoTexture(v);
      tex.colorSpace = THREE.SRGBColorSpace;
      group.userData.face.material.map = tex; group.userData.face.material.needsUpdate = true;
      renderOnce();
    }, {once: true});
    v.addEventListener("error", () => v.remove(), {once: true});       // no clip: the drawn card stays
    videos.push(v);
    if (!reduce) v.play().catch(() => {});
  }
  function playing(on) { videos.forEach(v => { if (on && !reduce) v.play().catch(() => {}); else v.pause(); }); }

  // ---- sparks: small bright points drifting behind the clips
  const N = 140, pos = new Float32Array(N * 3), seed = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    pos[i * 3] = (Math.random() - 0.5) * 22; pos[i * 3 + 1] = (Math.random() - 0.5) * 12; pos[i * 3 + 2] = -3 - Math.random() * 6;
    seed[i] = Math.random() * 6.28;
  }
  const sparkGeo = new THREE.BufferGeometry(); sparkGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const sparks = new THREE.Points(sparkGeo, new THREE.PointsMaterial({color: 0xffd0d0, size: 0.09, transparent: true, opacity: 0.8, depthWrite: false}));
  scene.add(sparks);

  // ---- the carousel's position: a continuous angle, so the clips glide instead of jumping
  let active = 0, target = 0, dragging = false, dragX = 0, dragStart = 0, hovered = null, idle = 0;
  const pointer = {x: 0, y: 0, sx: 0, sy: 0};
  const slot = r => ({
    x: r * 2.5,
    y: 0.12 - 0.42 * Math.abs(r),
    z: -1.6 * Math.abs(r),
    ry: -r * 0.42,
    rz: -r * 0.07
  });
  const wrap = v => { const m = ((v % 3) + 3) % 3; return m > 1.5 ? m - 3 : m; };

  function place(t) {
    cards.forEach((group, i) => {
      const r = wrap(i - active);
      const s = slot(r);
      const bob = reduce ? 0 : Math.sin(t * 0.8 + i * 1.7) * 0.06;
      const hot = hovered === group ? 1 : 0;
      group.userData.glow += (hot - group.userData.glow) * 0.18;
      group.position.set(s.x, s.y + bob, s.z + group.userData.glow * 0.35);
      group.rotation.set(0, s.ry, s.rz);
      const k = 1 + group.userData.glow * 0.06 - Math.abs(r) * 0.08;
      group.scale.setScalar(k);
      group.userData.face.material.emissiveIntensity = group.userData.glow * 0.22 + (Math.abs(r) < 0.5 ? 0.04 : 0);
    });
  }

  let raf = 0, visible = true, last = 0;
  function frame(now) {
    const t = now / 1000, dt = Math.min(0.05, (now - last) / 1000 || 0.016); last = now;
    if (!dragging && !reduce) {
      idle += dt;
      if (idle > 4.2 && !hovered) target += dt * 0.9;             // a slow turn while nobody is touching it
    }
    active += (target - active) * Math.min(1, dt * 6);
    pointer.sx += (pointer.x - pointer.sx) * 0.06; pointer.sy += (pointer.y - pointer.sy) * 0.06;
    carousel.rotation.y = pointer.sx * 0.1; carousel.rotation.x = pointer.sy * 0.05;
    sparks.rotation.z = t * 0.02; sparks.position.x = Math.sin(t * 0.15) * 0.25;
    place(t);
    renderer.render(scene, camera);
    raf = 0;
    if (visible && !reduce) raf = requestAnimationFrame(frame);   // keeps moving while on screen; still when reduced motion is on
  }
  function renderOnce() { if (!raf) raf = requestAnimationFrame(frame); }
  function kick() { if (!raf && visible) raf = requestAnimationFrame(frame); }

  // ---- size and visibility
  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    const narrow = w < 560;
    camera.position.z = narrow ? 14 : 11.5;                       // phones see the whole row of clips
    camera.updateProjectionMatrix();
    renderOnce();
  }
  new ResizeObserver(resize).observe(canvas);
  new IntersectionObserver(es => { visible = es[0].isIntersecting; playing(visible); if (visible) kick(); }, {threshold: 0}).observe(canvas);
  document.addEventListener("visibilitychange", () => { playing(!document.hidden && visible); if (!document.hidden) kick(); });

  // ---- interaction: hover, drag, click
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  function hit(e) {
    const r = canvas.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const found = ray.intersectObjects(cards.map(g => g.userData.face), false)[0];
    return found ? found.object.parent : null;
  }
  canvas.addEventListener("pointermove", e => {
    const r = canvas.getBoundingClientRect();
    pointer.x = ((e.clientX - r.left) / r.width - 0.5) * 2; pointer.y = ((e.clientY - r.top) / r.height - 0.5) * 2;
    if (dragging) {
      const dx = e.clientX - dragX;
      target = dragStart - dx / (r.width * 0.22);
    }
    hovered = dragging ? hovered : hit(e);
    canvas.style.cursor = dragging ? "grabbing" : hovered ? "pointer" : "grab";
    idle = 0; kick();
  });
  canvas.addEventListener("pointerleave", () => { hovered = null; pointer.x = 0; pointer.y = 0; kick(); });
  canvas.addEventListener("pointerdown", e => {
    dragging = true; dragX = e.clientX; dragStart = target; idle = 0;
    canvas.setPointerCapture(e.pointerId); canvas.style.cursor = "grabbing";
  });
  canvas.addEventListener("pointerup", e => {
    const moved = Math.abs(e.clientX - dragX);
    dragging = false; canvas.releasePointerCapture(e.pointerId);
    if (moved < 6) {                                              // a tap or click, not a drag
      const g = hit(e);
      if (g) {
        const i = g.userData.i;
        const r = wrap(i - active);
        if (Math.abs(r) > 0.5) target += r;                       // turn the carousel until this clip is in front
      }
    } else {
      target = Math.round(target);                                // settle on the nearest clip after a drag
    }
    kick();
  });
  canvas.addEventListener("keydown", e => {
    if (e.key === "ArrowRight") { target += 1; e.preventDefault(); }
    if (e.key === "ArrowLeft") { target -= 1; e.preventDefault(); }
    idle = 0; kick();
  });
  canvas.tabIndex = 0;

  build();
  resize();
  if (!reduce) kick();
}
