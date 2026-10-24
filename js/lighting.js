// Lighting environments. Each preset is a small HDR scene (a gradient sky
// sphere plus emissive panels: softboxes, windows, spotlights, the sun) that is
// captured into cube maps. Metals read a prefiltered copy; stones read a sharp
// copy so facets flash with crisp light shapes.
//
// World axes match the photo: +X right, +Y up, +Z toward the camera.

import * as THREE from 'three';
import { L } from './layers.js';

// Black-body colour (Tanner Helland fit), returned as linear RGB with max 1
export function kelvinToLinear(k) {
  const t = k / 100;
  let r, g, b;
  if (t <= 66) { r = 255; g = 99.4708025861 * Math.log(t) - 161.1195681661; }
  else { r = 329.698727446 * Math.pow(t - 60, -0.1332047592); g = 288.1221695283 * Math.pow(t - 60, -0.0755148492); }
  if (t >= 66) b = 255; else if (t <= 19) b = 0; else b = 138.5177312231 * Math.log(t - 10) - 305.0447927307;
  const lin = [r, g, b].map((v) => {
    const c = Math.min(255, Math.max(0, v)) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  const m = Math.max(...lin);
  return lin.map((v) => v / m);
}

// relative tint so that `k` looks neutral when the scene is balanced for 5600 K
function tintFor(k) {
  const c = kelvinToLinear(k), ref = kelvinToLinear(5600);
  const t = c.map((v, i) => v / ref[i]);
  const lum = 0.2126 * t[0] + 0.7152 * t[1] + 0.0722 * t[2];
  return t.map((v) => v / lum);
}

const rect = (dir, w, h, I, extra = {}) => ({ shape: 'rect', dir, w, h, I, ...extra });
const disc = (dir, d, I, extra = {}) => ({ shape: 'disc', dir, w: d, h: d, I, ...extra });

export const LIGHT_PRESETS = {
  studio: {
    label: "Jeweler's light tent", kelvin: 5500, sky: [1.15, 0.9, 0.55], uv: 0.08,
    key: [0, 0.9, 0.45], shadow: 0.4, shadowRadius: 9,
    emitters: [
      rect([0, 1, 0.3], 72, 46, 4.2),
      rect([0, -0.1, 1], 72, 18, 1.8),
      // black cards give metal and facets their contrast
      rect([-1, 0.12, 0.12], 26, 84, 0.015),
      rect([1, 0.12, 0.12], 26, 84, 0.015),
      rect([0, 0.28, -1], 64, 30, 0.02),
      rect([-0.5, 0.55, 0.65], 10, 26, 0.01),
      disc([-0.35, 0.75, 0.6], 2.6, 120),
      disc([0.45, 0.6, 0.65], 2.0, 130),
    ],
  },
  darkStudio: {
    label: 'Dark studio, softboxes', kelvin: 5500, sky: [0.05, 0.035, 0.018], uv: 0.08,
    key: [0, 0.9, 0.45], shadow: 0.42, shadowRadius: 9,
    emitters: [
      rect([0, 1, 0.35], 76, 46, 2.6),
      rect([-1, 0.25, 0.22], 14, 70, 3.4),
      rect([1, 0.25, 0.22], 14, 70, 3.4),
      rect([0, -0.12, 1], 70, 16, 0.9),
      disc([-0.35, 0.75, 0.6], 2.6, 160),
      disc([0.45, 0.6, 0.65], 2.0, 170),
    ],
  },
  window: {
    label: 'Window daylight', kelvin: 6300, sky: [0.32, 0.26, 0.12], skyKelvin: 4300, uv: 0.45,
    key: [-0.85, 0.3, 0.45], shadow: 0.55, shadowRadius: 3,
    emitters: [rect([-0.85, 0.3, 0.45], 46, 60, 7.5, { panes: [2, 3] }), rect([0, 1, 0], 40, 40, 0.6, { kelvin: 3800 })],
  },
  overcast: {
    label: 'Overcast outdoors', kelvin: 6800, sky: [2.1, 1.55, 0.26], groundKelvin: 5200, uv: 0.8,
    key: [0, 1, 0.3], shadow: 0.22, shadowRadius: 14, emitters: [],
  },
  sun: {
    label: 'Direct sunlight', kelvin: 5600, sky: [0.75, 1.3, 0.34], skyKelvin: 11000, groundKelvin: 4800, uv: 1,
    key: [0.45, 0.72, 0.52], shadow: 0.78, shadowRadius: 1.2,
    emitters: [disc([0.45, 0.72, 0.52], 1.0, 9000)],
  },
  office: {
    label: 'Office ceiling panels', kelvin: 4000, sky: [0.42, 0.33, 0.14], uv: 0.15,
    key: [0, 1, 0.2], shadow: 0.34, shadowRadius: 6,
    emitters: [-1, 0, 1].flatMap((x) => [-0.45, 0.35].map((z) => rect([x * 0.42, 1, z], 15, 15, 9))),
  },
  candle: {
    label: 'Candlelit dinner', kelvin: 2000, sky: [0.012, 0.008, 0.004], uv: 0,
    key: [0.15, 0.2, 1], shadow: 0.62, shadowRadius: 2,
    emitters: [
      disc([0.15, 0.18, 1], 2.4, 220), disc([-0.6, 0.5, 0.6], 1.6, 90), disc([0.7, 0.55, 0.45], 1.4, 110),
      disc([-0.2, 0.85, 0.5], 1.8, 80), disc([0.3, 0.9, -0.2], 1.2, 70), disc([-0.85, 0.35, -0.1], 1.4, 60),
    ],
  },
  golden: {
    label: 'Golden hour', kelvin: 3100, sky: [0.45, 0.95, 0.2], skyKelvin: 8000, horizonKelvin: 3000, uv: 0.5,
    key: [0.85, 0.2, 0.5], shadow: 0.7, shadowRadius: 2,
    emitters: [disc([0.85, 0.2, 0.5], 1.6, 3200)],
  },
  spots: {
    label: 'Evening spotlights', kelvin: 3600, sky: [0.022, 0.016, 0.01], uv: 0.05,
    key: [-0.2, 0.8, 0.55], shadow: 0.6, shadowRadius: 1.5,
    emitters: [
      disc([-0.2, 0.8, 0.55], 2.2, 380), disc([0.5, 0.6, 0.6], 1.6, 300), disc([-0.6, 0.45, 0.65], 1.4, 260),
      disc([0.1, 0.4, 0.9], 1.2, 240), disc([0.75, 0.3, 0.2], 1.8, 200), disc([-0.1, 0.95, -0.3], 2.4, 220),
    ],
  },
  lamp: {
    label: 'Warm table lamp', kelvin: 2800, sky: [0.06, 0.045, 0.025], uv: 0.02,
    key: [0.65, 0.45, 0.6], shadow: 0.5, shadowRadius: 5,
    emitters: [disc([0.65, 0.45, 0.6], 26, 5.5), rect([-0.9, 0.2, -0.3], 40, 50, 0.12, { kelvin: 9000, panes: [2, 2] })],
  },
  match: {
    label: 'Soft room light (photo colours)', kelvin: 5600, sky: [0.5, 0.45, 0.25], uv: 0.3, fromPhoto: true,
    key: [0, 0.85, 0.5], shadow: 0.38, shadowRadius: 8,
    emitters: [rect([0, 1, 0.4], 70, 50, 2.2), rect([0, 0.1, 1], 60, 25, 0.7)],
  },
};

const skyVertex = /* glsl */ `
varying vec3 vLocalDir;
varying vec3 vWorldDir;
void main() {
  vLocalDir = normalize( position );
  vec4 wp = modelMatrix * vec4( position, 1.0 );
  vWorldDir = normalize( wp.xyz - ( modelMatrix * vec4( 0.0, 0.0, 0.0, 1.0 ) ).xyz );
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;

const skyFragment = /* glsl */ `
uniform vec3 zenith;
uniform vec3 horizon;
uniform vec3 ground;
uniform sampler2D photo;
uniform float photoMix;
uniform float photoGain;
varying vec3 vLocalDir;
varying vec3 vWorldDir;
void main() {
  vec3 d = normalize( vLocalDir );
  vec3 c = d.y > 0.0 ? mix( horizon, zenith, pow( d.y, 0.7 ) ) : mix( horizon, ground, pow( - d.y, 0.45 ) );
  if ( photoMix > 0.0 ) {
    vec3 w = normalize( vWorldDir );
    // what lies behind and around the ring in the photo: the hand, the table, the room
    float back = smoothstep( 0.35, - 0.55, w.z );
    vec2 uv = 0.5 + 0.5 * w.xy / ( 1.0 + abs( w.z ) ) * 1.25;
    vec3 p = texture2D( photo, clamp( uv, 0.0, 1.0 ) ).rgb * photoGain;
    c = mix( c, p, back * photoMix );
  }
  gl_FragColor = vec4( c, 1.0 );
}`;

const panelFragment = /* glsl */ `
uniform vec3 color;
uniform float feather;
uniform vec2 panes;
uniform float isRound;
varying vec2 vUv;
void main() {
  vec2 q = vUv * 2.0 - 1.0;
  float m;
  if ( isRound > 0.5 ) {
    float r = length( q );
    m = 1.0 - smoothstep( 1.0 - feather, 1.0, r );
  } else {
    vec2 e = smoothstep( vec2( 1.0 ), vec2( 1.0 - feather ), abs( q ) );
    m = e.x * e.y;
    if ( panes.x > 0.5 ) {
      vec2 g = fract( vUv * panes );
      vec2 bar = step( vec2( 0.06 ), g ) * step( g, vec2( 0.94 ) );
      m *= mix( 0.04, 1.0, bar.x * bar.y );
    }
  }
  if ( m <= 0.001 ) discard;
  gl_FragColor = vec4( color * m, 1.0 );
}`;
const panelVertex = /* glsl */ `
varying vec2 vUv;
void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 ); }`;

export class Environment {
  constructor(scene) {
    this.group = new THREE.Group();
    this.group.name = 'environment';
    scene.add(this.group);
    this.radius = 1000;
    const photoTex = new THREE.DataTexture(new Uint8Array([128, 110, 100, 255]), 1, 1);
    photoTex.colorSpace = THREE.SRGBColorSpace;
    photoTex.needsUpdate = true;
    this.skyMat = new THREE.ShaderMaterial({
      vertexShader: skyVertex,
      fragmentShader: skyFragment,
      side: THREE.BackSide,
      depthWrite: false,
      uniforms: {
        zenith: { value: new THREE.Color() }, horizon: { value: new THREE.Color() }, ground: { value: new THREE.Color() },
        photo: { value: photoTex }, photoMix: { value: 0 }, photoGain: { value: 1 },
      },
    });
    this.sky = new THREE.Mesh(new THREE.SphereGeometry(this.radius, 64, 32), this.skyMat);
    this.sky.layers.set(L.ENV);
    this.sky.renderOrder = -10;
    this.group.add(this.sky);
    this.panels = new THREE.Group();
    this.group.add(this.panels);
    this.keyDir = new THREE.Vector3(0, 1, 0.4).normalize();
    this.ambient = new THREE.Vector3(0.2, 0.2, 0.2);
    this.preset = null;
  }

  setPhoto(texture, mix, gain = 1) {
    if (texture) this.skyMat.uniforms.photo.value = texture;
    this.skyMat.uniforms.photoMix.value = texture ? mix : 0;
    this.skyMat.uniforms.photoGain.value = gain;
  }

  // opts: { kelvin, azimuth (deg), elevation (deg), photoColor: [r,g,b] linear (for 'match') }
  build(key, opts = {}) {
    const p = LIGHT_PRESETS[key] || LIGHT_PRESETS.studio;
    this.preset = p;
    const kelvin = opts.kelvin || p.kelvin;
    const shift = tintFor(kelvin).map((v, i) => v / tintFor(p.kelvin)[i]);
    const light = tintFor(p.kelvin).map((v, i) => v * shift[i]);
    const skyT = tintFor(p.skyKelvin || p.kelvin).map((v, i) => v * shift[i]);
    const horT = tintFor(p.horizonKelvin || p.skyKelvin || p.kelvin).map((v, i) => v * shift[i]);
    const grT = tintFor(p.groundKelvin || p.skyKelvin || p.kelvin).map((v, i) => v * shift[i]);
    let [z, h, gr] = p.sky;
    const u = this.skyMat.uniforms;
    if (p.fromPhoto && opts.photoColor) {
      const pc = opts.photoColor;
      u.zenith.value.setRGB(pc[0] * z * 1.6, pc[1] * z * 1.6, pc[2] * z * 1.6);
      u.horizon.value.setRGB(pc[0] * h * 1.4, pc[1] * h * 1.4, pc[2] * h * 1.4);
      u.ground.value.setRGB(pc[0] * gr, pc[1] * gr, pc[2] * gr);
    } else {
      u.zenith.value.setRGB(z * skyT[0], z * skyT[1], z * skyT[2]);
      u.horizon.value.setRGB(h * horT[0], h * horT[1], h * horT[2]);
      u.ground.value.setRGB(gr * grT[0], gr * grT[1], gr * grT[2]);
    }

    for (const c of this.panels.children) { c.geometry.dispose(); c.material.dispose(); }
    this.panels.clear();
    const D = this.radius * 0.9;
    let energy = 0;
    for (const e of p.emitters) {
      const w = 2 * D * Math.tan(THREE.MathUtils.degToRad(e.w) / 2);
      const hh = 2 * D * Math.tan(THREE.MathUtils.degToRad(e.h) / 2);
      const t = e.kelvin ? tintFor(e.kelvin).map((v, i) => v * shift[i]) : light;
      const mat = new THREE.ShaderMaterial({
        vertexShader: panelVertex,
        fragmentShader: panelFragment,
        side: THREE.DoubleSide,
        depthWrite: false,
        uniforms: {
          color: { value: new THREE.Color(e.I * t[0], e.I * t[1], e.I * t[2]) },
          feather: { value: e.shape === 'disc' ? (e.w < 4 ? 0.5 : 0.12) : 0.1 },
          panes: { value: new THREE.Vector2(...(e.panes || [0, 0])) },
          isRound: { value: e.shape === "disc" ? 1 : 0 },
        },
      });
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, hh), mat);
      const dir = new THREE.Vector3(...e.dir).normalize();
      m.position.copy(dir).multiplyScalar(D);
      m.lookAt(0, 0, 0);
      m.layers.set(L.ENV);
      m.renderOrder = -9;
      this.panels.add(m);
      const solid = (w * hh) / (D * D);
      energy += e.I * solid * Math.max(0, dir.y * 0.5 + 0.5);
    }
    this.ambient.set(
      (u.zenith.value.r + u.horizon.value.r * 2 + u.ground.value.r) / 4 + energy * light[0] * 0.05,
      (u.zenith.value.g + u.horizon.value.g * 2 + u.ground.value.g) / 4 + energy * light[1] * 0.05,
      (u.zenith.value.b + u.horizon.value.b * 2 + u.ground.value.b) / 4 + energy * light[2] * 0.05
    );
    this.setRotation(opts.azimuth || 0, opts.elevation || 0);
  }

  setRotation(azimuthDeg, elevationDeg) {
    const e = new THREE.Euler(THREE.MathUtils.degToRad(-elevationDeg), 0, THREE.MathUtils.degToRad(-azimuthDeg), 'ZXY');
    this.group.quaternion.setFromEuler(e);
    this.group.updateMatrixWorld(true);
    const p = this.preset || LIGHT_PRESETS.studio;
    this.keyDir.set(...p.key).normalize().applyQuaternion(this.group.quaternion);
  }

  place(center) {
    this.group.position.copy(center);
    this.group.updateMatrixWorld(true);
  }
}
