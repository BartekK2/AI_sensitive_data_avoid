import { useEffect, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import modelUrl from "../../../tarcza_model.glb?url";

function paperToAlpha(texture) {
  const image = texture.image;
  const canvas = document.createElement("canvas");
  canvas.width = image.width;
  canvas.height = image.height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(image, 0, 0);
  const frame = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const px = frame.data;
  for (let i = 0; i < px.length; i += 4) {
    const r = px[i];
    const g = px[i + 1];
    const b = px[i + 2];
    const min = Math.min(r, g, b);
    const max = Math.max(r, g, b);
    const sat = max - min;
    const luma = r * 0.2126 + g * 0.7152 + b * 0.0722;
    // Paper is bright and almost neutral. Tinted lines stay, even when pale.
    if (sat <= 12 && luma >= 210) {
      px[i + 3] = 0;
    } else if (sat <= 20 && luma >= 196) {
      const fade = Math.min(1, (luma - 196) / 40);
      px[i + 3] = Math.round(255 * (1 - fade));
    }
  }
  ctx.putImageData(frame, 0, 0);
  const next = new THREE.CanvasTexture(canvas);
  next.colorSpace = THREE.SRGBColorSpace;
  next.flipY = false;
  next.anisotropy = 8;
  next.needsUpdate = true;
  return next;
}

export default function Strata() {
  const ref = useRef(null);

  useEffect(() => {
    const canvas = ref.current;
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.NoToneMapping;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(28, 1, 0.01, 20);
    const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
    let model = null;
    let halfH = 0.9;
    let halfW = 0.75;
    let raf = 0;
    let alive = true;
    const restYaw = -0.38;
    const restPitch = 0.05;

    const onMove = (event) => {
      const box = canvas.getBoundingClientRect();
      pointer.tx = (event.clientX - box.left) / box.width - 0.5;
      pointer.ty = (event.clientY - box.top) / box.height - 0.5;
    };
    const onLeave = () => {
      pointer.tx = 0;
      pointer.ty = 0;
    };
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerleave", onLeave);

    const fit = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (!w || !h) return;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      const vFov = (camera.fov * Math.PI) / 180;
      const hFov = 2 * Math.atan(Math.tan(vFov / 2) * camera.aspect);
      const distV = halfH / Math.tan(vFov / 2);
      const distH = halfW / Math.tan(hFov / 2);
      camera.position.z = Math.max(distV, distH) * 1.327;
      camera.lookAt(0, 0, 0);
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(fit);
    observer.observe(canvas);
    fit();

    const loader = new GLTFLoader();
    loader.load(modelUrl, (gltf) => {
      if (!alive) return;
      model = gltf.scene;
      model.traverse((node) => {
        if (!node.isMesh || !node.material) return;
        const source = Array.isArray(node.material) ? node.material : [node.material];
        const next = source.map((material) => {
          const basic = new THREE.MeshBasicMaterial({
            map: material.map ? paperToAlpha(material.map) : null,
            transparent: true,
            alphaTest: 0.04,
            depthWrite: true,
            side: THREE.FrontSide,
          });
          return basic;
        });
        node.material = next.length === 1 ? next[0] : next;
      });
      const bounds = new THREE.Box3().setFromObject(model);
      const center = bounds.getCenter(new THREE.Vector3());
      const size = bounds.getSize(new THREE.Vector3());
      model.position.sub(center);
      const maxYaw = restYaw - 0.09;
      const maxPitch = restPitch + 0.05;
      halfH = size.y / 2 + (size.z / 2) * Math.sin(maxPitch);
      halfW = (size.x / 2) * Math.abs(Math.cos(maxYaw)) + (size.z / 2) * Math.abs(Math.sin(maxYaw));
      model.rotation.y = restYaw;
      scene.add(model);
      fit();
    });

    const frame = () => {
      pointer.x += (pointer.tx - pointer.x) * 0.08;
      pointer.y += (pointer.ty - pointer.y) * 0.08;
      if (model) {
        const yaw = restYaw + Math.max(-0.5, Math.min(0.5, pointer.x)) * 0.18;
        const pitch = restPitch + Math.max(-0.5, Math.min(0.5, pointer.y)) * 0.1;
        model.rotation.y = yaw;
        model.rotation.x = pitch;
      }
      renderer.render(scene, camera);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      observer.disconnect();
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
      renderer.dispose();
    };
  }, []);

  return <canvas ref={ref} className="strata" aria-label="Tarcza" />;
}
