// 3D sunlight preview. Renders the target unit, surrounding building prisms,
// and an animated sun that casts real shadows. All geometry and every sun
// position come straight from the /api/assess response (the deterministic
// engine) - this module only visualises; it computes no sunlight itself.
//
// World frame:  X = East,  Y = Up,  Z = South  (so North = -Z).
// Sun unit vector for altitude `alt` and compass azimuth `A` (0=N,90=E,180=S):
//   ( cos(alt)*sin(A),  sin(alt),  -cos(alt)*cos(A) )

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const M_PER_DEG_LAT = 111132.0;
const mPerDegLon = (lat) => 111320.0 * Math.cos(lat * Math.PI / 180);
const DAY_LABELS = {
  winter_solstice: 'Winter solstice (21 Dec)',
  spring_equinox: 'Equinox (20 Mar)',
  summer_solstice: 'Summer solstice (21 Jun)',
};

let renderer, scene, camera, controls, sunLight, sunSphere, sunBeam;
let buildingGroup, windowMarker, groundMat;
let days = {};                 // dayName -> [{time,altitude,azimuth,direct}]
let arcGroup;                  // colored sun-path points for the current day
let curDay = 'summer_solstice';
let curPoints = [];            // above-horizon points of curDay
let curIdx = 0;
let playing = false;
let facadeAz = 180, windowH = 12;
let sceneReady = false;

function el(id) { return document.getElementById(id); }

function sunVector(altDeg, azDeg) {
  const a = altDeg * Math.PI / 180, z = azDeg * Math.PI / 180;
  return new THREE.Vector3(
    Math.cos(a) * Math.sin(z),
    Math.sin(a),
    -Math.cos(a) * Math.cos(z),
  );
}

function init() {
  const canvas = el('sceneCanvas');
  if (!canvas) return false;
  const w = canvas.clientWidth || 800, h = canvas.clientHeight || 460;

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
  renderer.setSize(w, h, false);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x9fc4e8);

  camera = new THREE.PerspectiveCamera(50, w / h, 1, 5000);
  camera.position.set(140, 120, 200);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 15, 0);
  controls.maxPolarAngle = Math.PI / 2 - 0.02; // stay above ground
  controls.update();

  scene.add(new THREE.HemisphereLight(0xbcd7f2, 0x4a4436, 0.85));
  const fill = new THREE.AmbientLight(0xffffff, 0.25);
  scene.add(fill);

  sunLight = new THREE.DirectionalLight(0xfff2d0, 2.2);
  sunLight.castShadow = true;
  sunLight.shadow.mapSize.set(2048, 2048);
  const s = 260;
  Object.assign(sunLight.shadow.camera, { left: -s, right: s, top: s, bottom: -s, near: 1, far: 1400 });
  sunLight.shadow.bias = -0.0004;
  scene.add(sunLight);
  scene.add(sunLight.target);

  // Ground
  groundMat = new THREE.MeshLambertMaterial({ color: 0x3f7a3f });
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(2000, 2000), groundMat);
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
  const grid = new THREE.GridHelper(2000, 100, 0x2f5f2f, 0x2f5f2f);
  grid.material.opacity = 0.25; grid.material.transparent = true;
  scene.add(grid);

  // Compass markers (N/E/S/W) on the ground
  addCompass();

  // Sun sphere + beam toward the target window
  sunSphere = new THREE.Mesh(
    new THREE.SphereGeometry(6, 20, 20),
    new THREE.MeshBasicMaterial({ color: 0xffd24d }),
  );
  scene.add(sunSphere);
  sunBeam = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
    new THREE.LineBasicMaterial({ color: 0xffe27a, transparent: true, opacity: 0.5 }),
  );
  scene.add(sunBeam);

  buildingGroup = new THREE.Group();
  scene.add(buildingGroup);
  arcGroup = new THREE.Group();
  scene.add(arcGroup);

  window.addEventListener('resize', onResize);
  wireUI();
  animate();
  sceneReady = true;
  return true;
}

function addCompass() {
  const mk = (txt, x, z, color) => {
    const cv = document.createElement('canvas'); cv.width = cv.height = 64;
    const ctx = cv.getContext('2d');
    ctx.fillStyle = color; ctx.font = 'bold 44px sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(txt, 32, 34);
    const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(cv), transparent: true }));
    spr.position.set(x, 4, z); spr.scale.set(22, 22, 1);
    scene.add(spr);
  };
  mk('N', 0, -150, '#fff'); mk('S', 0, 150, '#fff');
  mk('E', 150, 0, '#fff'); mk('W', -150, 0, '#fff');
}

function clearGroup(g) { while (g.children.length) { const c = g.children.pop(); c.geometry?.dispose?.(); g.remove(c); } }

function buildBuildings(data) {
  clearGroup(buildingGroup);
  const loc = data.location || {};
  const lat0 = loc.lat, lon0 = loc.lon;
  if (lat0 == null) return;
  const mLon = mPerDegLon(lat0);
  const targetId = data.assessment?.target_inside_building || null;

  for (const b of (data.buildings || [])) {
    const ring = b.footprint;
    if (!ring || ring.length < 4) continue;
    const shape = new THREE.Shape();
    ring.forEach(([lon, lat], i) => {
      const east = (lon - lon0) * mLon;
      const north = (lat - lat0) * M_PER_DEG_LAT;
      i === 0 ? shape.moveTo(east, north) : shape.lineTo(east, north);
    });
    const height = Math.max(2, b.height_m || 6);
    let geom;
    try {
      geom = new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false });
    } catch (e) { continue; }

    const isTarget = targetId && b.source_id === targetId;
    const color = isTarget ? 0xff8a3d : (b.estimated ? 0xb59b63 : 0x6f8db0);
    const mat = new THREE.MeshLambertMaterial({
      color, transparent: isTarget, opacity: isTarget ? 0.55 : 1.0,
    });
    const mesh = new THREE.Mesh(geom, mat);
    mesh.rotation.x = -Math.PI / 2;   // shape(East,North) extruded up -> X=East, Y=up, Z=South
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    buildingGroup.add(mesh);
  }

  // Window marker on the target facade, at the computed window height.
  if (windowMarker) { scene.remove(windowMarker); windowMarker.geometry.dispose(); }
  const n = sunVector(0, facadeAz); // facade outward normal in the horizontal plane
  windowMarker = new THREE.Mesh(
    new THREE.BoxGeometry(6, 4, 1.2),
    new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0x222222, emissiveIntensity: 1 }),
  );
  windowMarker.position.set(n.x * 3, windowH, n.z * 3);
  windowMarker.lookAt(windowMarker.position.clone().add(n));
  scene.add(windowMarker);
}

function buildArc() {
  clearGroup(arcGroup);
  curPoints = (days[curDay] || []).filter((p) => p.altitude > 0);
  const R = 230;
  for (const p of curPoints) {
    const v = sunVector(p.altitude, p.azimuth).multiplyScalar(R);
    const dot = new THREE.Mesh(
      new THREE.SphereGeometry(2.4, 10, 10),
      new THREE.MeshBasicMaterial({ color: p.direct_sun ? 0xffcf33 : 0x8a97a6 }),
    );
    dot.position.copy(v);
    arcGroup.add(dot);
  }
  const slider = el('sceneSlider');
  slider.min = 0; slider.max = Math.max(0, curPoints.length - 1);
  // default to solar noon (highest sun)
  let hi = 0; curPoints.forEach((p, i) => { if (p.altitude > curPoints[hi].altitude) hi = i; });
  curIdx = curPoints.length ? hi : 0;
  slider.value = curIdx;
  applyIdx();
}

function applyIdx() {
  const p = curPoints[curIdx];
  const status = el('sceneStatus');
  if (!p) { if (status) status.textContent = 'Sun below horizon all listed steps.'; return; }
  const R = 230;
  const dir = sunVector(p.altitude, p.azimuth);
  const pos = dir.clone().multiplyScalar(R);
  sunLight.position.copy(pos);
  sunLight.target.position.set(0, windowH, 0);
  sunLight.intensity = 0.6 + 1.9 * Math.sin(p.altitude * Math.PI / 180);
  sunSphere.position.copy(pos);

  // beam from sun to the window marker; bright gold if direct sun reaches it
  const wp = windowMarker ? windowMarker.position : new THREE.Vector3(0, windowH, 0);
  sunBeam.geometry.setFromPoints([pos, wp]);
  sunBeam.material.color.set(p.direct_sun ? 0xffca28 : 0x64748b);
  sunBeam.material.opacity = p.direct_sun ? 0.75 : 0.2;
  if (windowMarker) {
    windowMarker.material.emissive.set(p.direct_sun ? 0xffcf33 : 0x1b2733);
    windowMarker.material.emissiveIntensity = p.direct_sun ? 1.4 : 0.4;
  }
  scene.background.set(p.altitude < 6 ? 0xdcae7a : 0x9fc4e8); // warm near sunrise/set

  if (status) {
    status.innerHTML = `<b>${p.time}</b> · sun ${p.altitude.toFixed(0)}° high, `
      + `${p.azimuth.toFixed(0)}° az · `
      + (p.direct_sun
        ? '<span style="color:#c9820a">☀ direct sun reaches this window</span>'
        : '<span style="color:#64748b">blocked / wrong side</span>');
  }
}

function wireUI() {
  const daySel = el('sceneDay');
  if (daySel) {
    daySel.innerHTML = Object.entries(DAY_LABELS)
      .map(([k, v]) => `<option value="${k}"${k === curDay ? ' selected' : ''}>${v}</option>`).join('');
    daySel.onchange = () => { curDay = daySel.value; buildArc(); };
  }
  el('sceneSlider').oninput = (e) => { curIdx = +e.target.value; applyIdx(); };
  const playBtn = el('scenePlay');
  playBtn.onclick = () => { playing = !playing; playBtn.textContent = playing ? '⏸ Pause' : '▶ Play day'; };
}

let last = 0;
function animate(t) {
  requestAnimationFrame(animate);
  controls.update();
  if (playing && curPoints.length && t - last > 220) {
    last = t;
    curIdx = (curIdx + 1) % curPoints.length;
    el('sceneSlider').value = curIdx;
    applyIdx();
  }
  renderer.render(scene, camera);
}

function onResize() {
  const canvas = el('sceneCanvas');
  if (!canvas) return;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  camera.aspect = w / h; camera.updateProjectionMatrix();
  renderer.setSize(w, h, false);
}

function frameCamera(data) {
  // pull camera back based on the spread of building footprints
  let maxR = 80;
  const loc = data.location || {}; const lat0 = loc.lat, lon0 = loc.lon;
  if (lat0 != null) {
    const mLon = mPerDegLon(lat0);
    for (const b of (data.buildings || [])) {
      for (const [lon, lat] of (b.footprint || [])) {
        const e = (lon - lon0) * mLon, nn = (lat - lat0) * M_PER_DEG_LAT;
        maxR = Math.max(maxR, Math.hypot(e, nn));
      }
    }
  }
  maxR = Math.min(maxR, 260);
  camera.position.set(maxR * 0.7, maxR * 0.9, maxR * 1.25);
  controls.target.set(0, windowH, 0);
  controls.update();
}

function update(data) {
  if (!sceneReady && !init()) return;
  const a = data.assessment || {};
  if (a.assumptions) {
    facadeAz = a.assumptions.facade_azimuth_deg ?? 180;
    windowH = a.assumptions.window_height_m ?? 12;
  }
  days = a.representative_days || {};
  const panel = el('scenePanel');
  if (panel) panel.classList.remove('hidden');
  buildBuildings(data);
  frameCamera(data);
  // keep the selected day if present, else fall back
  if (!days[curDay]) curDay = Object.keys(days)[0] || curDay;
  const daySel = el('sceneDay'); if (daySel) daySel.value = curDay;
  buildArc();
  onResize();
}

window.SunScene = {
  update,
  debug: () => ({
    buildings: buildingGroup ? buildingGroup.children.length : 0,
    arcDots: arcGroup ? arcGroup.children.length : 0,
    hasWindowMarker: !!windowMarker,
    renderCalls: renderer ? renderer.info.render.calls : -1,
    triangles: renderer ? renderer.info.render.triangles : -1,
    sunPos: sunSphere ? sunSphere.position.toArray().map((n) => Math.round(n)) : null,
    curDay, curIdx, nPoints: curPoints.length,
  }),
};
