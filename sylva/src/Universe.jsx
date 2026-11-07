import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Plus, Minus, RotateCcw, Maximize2, Orbit } from "lucide-react";

const positions = [
  [-2.2, 1.12, 0.4],
  [2.15, 0.85, 0.65],
  [1.9, -1.5, 0.25],
  [-1.95, -1.5, -0.2],
  [0.2, 2.2, -0.5],
  [-0.4, -2.35, 0.3],
  [2.7, -0.2, -0.6],
  [-2.65, -0.1, 0.4],
];
const positionFor = (star, i, compact) => {
  let hash = 0;
  for (const c of star.id) hash = (hash * 31 + c.charCodeAt(0)) >>> 0;
  const index = star.layoutIndex ?? i;
  if (!compact && index >= positions.length) {
    const angle = index * Math.PI * (3 - Math.sqrt(5));
    const radius = 2.05 + ((index * Math.SQRT2) % 1) * 1.5;
    return new THREE.Vector3(
      Math.cos(angle) * radius * 1.5,
      Math.sin(angle) * radius * 0.75,
      (hash % 100) / 100 - 0.6,
    );
  }
  const base = positions[index % positions.length];
  const ring = Math.floor(index / positions.length);
  return new THREE.Vector3(
    base[0] * (1 + ring * 0.12),
    base[1] * (1 + ring * 0.12),
    base[2] + (hash % 20) / 50,
  );
};

const constellationCenters = [
  [-6.5, 1.45], [-4.35, -1.3], [-2.95, 2.1], [-1.05, -2.1],
  [0.9, 2.25], [2.85, -1.9], [4.4, 1.25], [6.4, -0.65],
];

function addConstellations(world, random, orbitColor) {
  const points = [];
  const lights = [];
  const edges = [];
  let previousHub;
  for (const [x, y] of constellationCenters) {
    const hub = new THREE.Vector3(x, y, -1.1 - random() * 1.5);
    const cluster = [hub];
    if (previousHub) edges.push(previousHub, hub);
    previousHub = hub;
    lights.push(hub);

    for (let i = 0; i < 16; i++) {
      const angle = i * Math.PI * (3 - Math.sqrt(5)) + random() * 0.55;
      const radius = Math.sqrt((i + 1) / 16) * (0.7 + random() * 0.55);
      const point = new THREE.Vector3(
        hub.x + Math.cos(angle) * radius * 1.65,
        hub.y + Math.sin(angle) * radius,
        hub.z + (random() - 0.5) * 0.8,
      );
      const nearest = cluster.reduce((a, b) =>
        point.distanceToSquared(b) < point.distanceToSquared(a) ? b : a,
      );
      edges.push(nearest, point);
      cluster.push(point);
      (i % 4 === 0 ? lights : points).push(point);
    }
  }

  world.add(
    new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints(edges),
      new THREE.LineBasicMaterial({
        color: orbitColor, transparent: true, opacity: 0.27, depthWrite: false,
      }),
    ),
  );
  for (const [nodes, size, opacity] of [[points, 0.047, 0.67], [lights, 0.081, 0.84]]) {
    world.add(
      new THREE.Points(
        new THREE.BufferGeometry().setFromPoints(nodes),
        new THREE.PointsMaterial({
          color: orbitColor, size, opacity, transparent: true, depthWrite: false,
        }),
      ),
    );
  }
}

export default function Universe({
  stars = [],
  childName = "你的孩子",
  compact = false,
  onSelect,
  newStarId,
  selectedId,
  onLit,
}) {
  const host = useRef(null),
    sceneAPI = useRef(null),
    onSelectRef = useRef(onSelect),
    onLitRef = useRef(onLit),
    labels = useRef({}),
    planetLabel = useRef(null);
  const [failed, setFailed] = useState(false),
    [paused, setPaused] = useState(false),
    [exploring, setExploring] = useState(false);
  onSelectRef.current = onSelect;
  onLitRef.current = onLit;
  const identity = stars.map((s) => s.id).join("|");
  useEffect(() => {
    const node = host.current;
    if (!node) return;
    setExploring(false);
    setPaused(false);
    let renderer,
      frame,
      disposed = false,
      controls,
      resize,
      observer;
    const resources = [];
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    try {
      const tokens = getComputedStyle(node);
      const starColor = tokens.getPropertyValue("--star").trim();
      const orbitColor = tokens.getPropertyValue("--orbit").trim();
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "low-power",
      });
      renderer.setPixelRatio(Math.min(devicePixelRatio, compact ? 1.5 : 2));
      renderer.setClearColor(0x000000, 0);
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.15;
      node.prepend(renderer.domElement);
      const scene = new THREE.Scene();
      scene.fog = new THREE.FogExp2(0x000000, 0.018);
      const environmentRoom = new RoomEnvironment();
      const pmrem = new THREE.PMREMGenerator(renderer);
      const environmentMap = pmrem.fromScene(environmentRoom, 0.04);
      scene.environment = environmentMap.texture;
      resources.push(() => {
        environmentMap.dispose();
        environmentRoom.dispose();
        pmrem.dispose();
      });
      const camera = new THREE.PerspectiveCamera(39, 1, 0.1, 100);
      camera.position.set(0, 0.25, compact ? 9.6 : 10.2);
      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.enablePan = false;
      controls.enableZoom = false;
      controls.minDistance = 7;
      controls.maxDistance = 15;
      controls.maxPolarAngle = Math.PI * 0.78;
      controls.minPolarAngle = Math.PI * 0.22;
      controls.autoRotate = false;
      controls.rotateSpeed = 0.4;
      renderer.domElement.style.touchAction = "pan-y";
      controls.enabled = false;
      scene.add(new THREE.AmbientLight(0xffffff, 0.5));
      const light = new THREE.DirectionalLight(starColor, 2);
      light.position.set(-3, 4, 5);
      scene.add(light);
      const rim = new THREE.PointLight(0xd4afc8, 24, 18);
      rim.position.set(3, 1, -2);
      scene.add(rim);
      const world = new THREE.Group();
      scene.add(world);
      const liquidGeometry = new THREE.SphereGeometry(1.12, 72, 48);
      const liquidVertices = liquidGeometry.attributes.position;
      for (let i = 0; i < liquidVertices.count; i++) {
        const x = liquidVertices.getX(i),
          y = liquidVertices.getY(i),
          z = liquidVertices.getZ(i);
        const warp =
          1 +
          0.115 * Math.sin(y * 5 + z * 2) +
          0.075 * Math.cos(x * 7 - z * 4) +
          0.045 * Math.sin(z * 9 + x * 3);
        liquidVertices.setXYZ(i, x * warp, y * warp, z * warp);
      }
      liquidGeometry.computeVertexNormals();
      const globe = new THREE.Mesh(
        liquidGeometry,
        new THREE.MeshPhysicalMaterial({
          color: 0xe2e5e7,
          roughness: 0.055,
          metalness: 1,
          clearcoat: 1,
          clearcoatRoughness: 0.03,
          envMapIntensity: 2.2,
        }),
      );
      if (compact) globe.scale.setScalar(1.2);
      world.add(globe);
      const grid = new THREE.LineSegments(
        new THREE.WireframeGeometry(new THREE.SphereGeometry(1.063, 24, 12)),
        new THREE.LineBasicMaterial({
          color: orbitColor,
          transparent: true,
          opacity: 0.15,
        }),
      );
      grid.visible = false;
      world.add(grid);
      const atmosphere = new THREE.Mesh(
        new THREE.SphereGeometry(1.15, 32, 24),
        new THREE.MeshBasicMaterial({
          color: starColor,
          transparent: true,
          opacity: 0.03,
          side: THREE.BackSide,
        }),
      );
      world.add(atmosphere);
      for (let i = 0; i < 3; i++) {
        const ring = new THREE.Mesh(
          new THREE.TorusGeometry(
            1.6 + i * 0.32,
            i === 0 ? 0.017 : 0.004,
            8,
            180,
          ),
          new THREE.MeshBasicMaterial({
            color: i === 0 ? 0xc8d1d3 : i === 1 ? starColor : 0xd4afc8,
            transparent: true,
            opacity: i === 0 ? 0.8 : 0.45,
          }),
        );
        ring.rotation.set(
          Math.PI * 0.3 + i * 0.32,
          0.35 + i * 0.5,
          -0.3 + i * 0.25,
        );
        world.add(ring);
      }
      let seed = 2531;
      const random = () => {
        seed = (seed * 1664525 + 1013904223) >>> 0;
        return seed / 4294967296;
      };
      if (!compact) addConstellations(world, random, orbitColor);
      const dustGeometry = new THREE.BufferGeometry(),
        dust = new Float32Array(560 * 3);
      for (let i = 0; i < dust.length; i += 3) {
        dust[i] = (random() - 0.5) * 29;
        dust[i + 1] = (random() - 0.5) * 22;
        dust[i + 2] = -random() * 12 - 1;
      }
      dustGeometry.setAttribute("position", new THREE.BufferAttribute(dust, 3));
      const dustPoints = new THREE.Points(
        dustGeometry,
        new THREE.PointsMaterial({
          color: 0xced3ba,
          size: 0.018,
          transparent: true,
          opacity: 0.65,
        }),
      );
      scene.add(dustPoints);
      const starMeshes = [];
      const previousBySport = new Map();
      const recordEdges = [];
      stars.forEach((star, i) => {
        const pos = positionFor(star, i, compact);
        const starGroup = new THREE.Group();
        starGroup.position.copy(pos);
        world.add(starGroup);
        const core = new THREE.Mesh(
          new THREE.IcosahedronGeometry(0.064, 1),
          new THREE.MeshBasicMaterial({ color: starColor }),
        );
        core.userData = { star };
        starGroup.add(core);
        const halo = new THREE.Mesh(
          new THREE.SphereGeometry(0.135, 16, 12),
          new THREE.MeshBasicMaterial({
            color: starColor,
            transparent: true,
            opacity: 0.09,
          }),
        );
        starGroup.add(halo);
        const hit = new THREE.Mesh(
          new THREE.SphereGeometry(0.25, 10, 8),
          new THREE.MeshBasicMaterial({ visible: false }),
        );
        hit.userData = { star };
        starGroup.add(hit);
        starMeshes.push({ star, group: starGroup, core, halo, hit, pos });
        const neighbor = !compact && previousBySport.get(star.sport);
        recordEdges.push(neighbor || pos.clone().normalize().multiplyScalar(1.12), pos);
        previousBySport.set(star.sport, pos);
      });
      world.add(
        new THREE.LineSegments(
          new THREE.BufferGeometry().setFromPoints(recordEdges),
          new THREE.LineBasicMaterial({
            color: orbitColor,
            transparent: true,
            opacity: compact ? 0.24 : 0.55,
          }),
        ),
      );
      const raycaster = new THREE.Raycaster(),
        pointer = new THREE.Vector2();
      let down;
      let hoveredLabel;
      const hits = starMeshes.map((s) => s.hit);
      const hitAt = (e) => {
        const rect = renderer.domElement.getBoundingClientRect();
        pointer.set(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          (-(e.clientY - rect.top) / rect.height) * 2 + 1,
        );
        raycaster.setFromCamera(pointer, camera);
        return raycaster.intersectObjects(hits)[0]?.object.userData.star;
      };
      const showHover = (label) => {
        if (hoveredLabel === label) return;
        hoveredLabel?.classList.remove("is-hovered");
        hoveredLabel = label;
        hoveredLabel?.classList.add("is-hovered");
      };
      const pointerMove = (e) => {
        const star = !e.buttons && hitAt(e);
        showHover(star ? labels.current[star.id] : undefined);
      };
      const pointerLeave = () => showHover(undefined);
      const pointerDown = (e) => {
        down = [e.clientX, e.clientY];
      };
      const pointerUp = (e) => {
        if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 7)
          return;
        const star = hitAt(e);
        if (star) onSelectRef.current?.(star);
      };
      renderer.domElement.addEventListener("pointerdown", pointerDown);
      renderer.domElement.addEventListener("pointerup", pointerUp);
      if (!compact) {
        renderer.domElement.addEventListener("pointermove", pointerMove);
        renderer.domElement.addEventListener("pointerleave", pointerLeave);
      }
      const contextLost = (e) => {
        e.preventDefault();
        setFailed(true);
      };
      renderer.domElement.addEventListener("webglcontextlost", contextLost);
      resize = () => {
        const { width, height } = node.getBoundingClientRect();
        if (width && height) {
          renderer.setSize(width, height);
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
        }
      };
      observer = new ResizeObserver(resize);
      observer.observe(node);
      resize();
      let lighting = null;
      sceneAPI.current = {
        nudge: (horizontal, vertical) => {
          camera.position.applyAxisAngle(
            new THREE.Vector3(0, 1, 0),
            horizontal,
          );
          camera.position.y = Math.max(
            -4,
            Math.min(4, camera.position.y + vertical),
          );
        },
        zoom: (delta) => {
          camera.position.multiplyScalar(delta);
          const length = camera.position.length();
          if (length < 7) camera.position.setLength(7);
          if (length > 15) camera.position.setLength(15);
        },
        reset: () => {
          camera.position.set(0, 0.25, compact ? 9.6 : 10.2);
          controls.target.set(0, 0, 0);
        },
        explore: (enable) => {
          controls.enabled = enable;
          renderer.domElement.style.touchAction = enable ? "none" : "pan-y";
        },
        light: (id) => {
          const target = starMeshes.find((s) => s.star.id === id);
          lighting = {
            id,
            start: performance.now(),
            done: false,
            from: controls.target.clone(),
            to: target
              ? target.pos.clone().multiplyScalar(0.55)
              : new THREE.Vector3(),
          };
        },
        pause: (value) => {
          sceneAPI.current.paused = value;
        },
        paused: false,
      };
      const animate = (time) => {
        if (disposed) return;
        frame = requestAnimationFrame(animate);
        if (document.hidden) return;
        if (lighting && !lighting.focused) {
          const progress = Math.min((time - lighting.start) / 800, 1);
          controls.target.lerpVectors(
            lighting.from,
            lighting.to,
            reduced ? 1 : 1 - Math.pow(1 - progress, 3),
          );
          if (progress === 1) lighting.focused = true;
        }
        controls.update();
        if (
          !reduced &&
          !sceneAPI.current?.paused &&
          document.documentElement.dataset.motion !== "paused"
        ) {
          grid.rotation.y += 0.0007;
          globe.rotation.y += 0.002;
          globe.rotation.z = Math.sin(time * 0.0002) * 0.12;
          globe.position.y = Math.sin(time * 0.0004) * 0.055;
        }
        for (const star of starMeshes) {
          let scale = 1;
          if (lighting?.id === star.star.id) {
            const elapsed = time - lighting.start;
            scale = reduced
              ? 1
              : 1 + Math.sin(Math.min(elapsed / 1600, 1) * Math.PI) * 2.2;
            star.halo.material.opacity = reduced
              ? 0.16
              : 0.12 + Math.sin(Math.min(elapsed / 1800, 1) * Math.PI) * 0.4;
            if (elapsed > 2350 && !lighting.done) {
              lighting.done = true;
              onLitRef.current?.(star.star.id);
            }
          }
          star.core.scale.setScalar(scale);
          const label = labels.current[star.star.id];
          if (label) {
            const p = star.group
              .getWorldPosition(new THREE.Vector3())
              .project(camera);
            const half = label.offsetWidth / 2;
            const x = Math.max(
              half + 8,
              Math.min(
                node.clientWidth - half - 8,
                (p.x * 0.5 + 0.5) * node.clientWidth,
              ),
            );
            label.style.transform = `translate(-50%,0) translate(${x}px,${(-p.y * 0.5 + 0.5) * node.clientHeight + 13}px)`;
            label.style.visibility = Math.abs(p.z) > 1 ? "hidden" : "";
          }
        }
        if (planetLabel.current) {
          const center = new THREE.Vector3().project(camera);
          planetLabel.current.style.left =
            (center.x * 0.5 + 0.5) * node.clientWidth + "px";
          planetLabel.current.style.top =
            (-center.y * 0.5 + 0.5) * node.clientHeight + "px";
        }
        renderer.render(scene, camera);
      };
      frame = requestAnimationFrame(animate);
      resources.push(() => {
        showHover(undefined);
        renderer.domElement.removeEventListener("pointerdown", pointerDown);
        renderer.domElement.removeEventListener("pointerup", pointerUp);
        renderer.domElement.removeEventListener("pointermove", pointerMove);
        renderer.domElement.removeEventListener("pointerleave", pointerLeave);
        renderer.domElement.removeEventListener(
          "webglcontextlost",
          contextLost,
        );
      });
      resources.push(() => {
        scene.traverse((o) => {
          o.geometry?.dispose();
          if (o.material) {
            const materials = Array.isArray(o.material)
              ? o.material
              : [o.material];
            materials.forEach((m) => m.dispose());
          }
        });
      });
    } catch (error) {
      console.warn("3D view unavailable; using accessible growth view.", error);
      setFailed(true);
    }
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer?.disconnect();
      controls?.dispose();
      resources.forEach((fn) => fn());
      renderer?.dispose();
      renderer?.domElement.remove();
      sceneAPI.current = null;
    };
  }, [identity, compact]);
  useEffect(() => {
    if (newStarId) sceneAPI.current?.light(newStarId);
  }, [newStarId, identity]);
  return (
    <div className={`universe ${compact ? "universe-compact" : ""}${!compact && stars.length > 8 ? " universe-dense" : ""}`}>
      <div className="universe-kicker">
        <span className="live-dot" />{" "}
        {compact ? "GROWTH, IN ORBIT" : "YOUR PERSONAL UNIVERSE"}
        <span className="mono">
          {String(stars.length).padStart(2, "0")} STARS
        </span>
      </div>
      <div
        ref={host}
        className={`universe-canvas ${failed ? "is-fallback" : ""}`}
        role="group"
        tabIndex={compact ? -1 : 0}
        onKeyDown={(event) => {
          if (compact || !event.key.startsWith("Arrow")) return;
          event.preventDefault();
          sceneAPI.current?.nudge(
            event.key === "ArrowLeft"
              ? -0.12
              : event.key === "ArrowRight"
                ? 0.12
                : 0,
            event.key === "ArrowUp"
              ? 0.25
              : event.key === "ArrowDown"
                ? -0.25
                : 0,
          );
        }}
        aria-label={`${childName}的互动成长宇宙`}
      >
        {failed ? (
          <div className="universe-fallback">
            <Orbit size={50} />
            <h3>{childName}的成长星图</h3>
            <p>已切换为平面记录视图</p>
            {stars.map((s) => (
              <button key={s.id} onClick={() => onSelect?.(s)}>
                {s.title} ↗
              </button>
            ))}
          </div>
        ) : (
          stars.map((star) => (
            <button
              className={`space-label${selectedId === star.id ? " is-selected" : ""}${newStarId === star.id ? " is-lighting" : ""}`}
              key={star.id}
              ref={(el) => {
                labels.current[star.id] = el;
              }}
              onClick={() => onSelect?.(star)}
              aria-label={`查看成长星星：${star.title}`}
            >
              <span>{star.sport}</span>
              {star.title}
            </button>
          ))
        )}
        {!failed && (
          <div ref={planetLabel} className="planet-name">
            <span>{childName}</span>
            <small>THE CENTER OF YOUR WORLD</small>
          </div>
        )}
      </div>
      <div className="universe-caption">
        <span>
          {stars.length
            ? "每一次尝试，都在这里闪耀。"
            : "第一颗星，从一次喜欢的运动开始。"}
        </span>
        {!compact && (
          <div className="space-controls">
            <button
              aria-label="放大星图"
              onClick={() => sceneAPI.current?.zoom(0.87)}
            >
              <Plus size={16} />
            </button>
            <button
              aria-label="缩小星图"
              onClick={() => sceneAPI.current?.zoom(1.13)}
            >
              <Minus size={16} />
            </button>
            <button
              aria-label="重置星图视角"
              onClick={() => sceneAPI.current?.reset()}
            >
              <RotateCcw size={16} />
            </button>
            <button
              aria-label="暂停星球转动"
              onClick={() => {
                setPaused(!paused);
                sceneAPI.current?.pause(!paused);
              }}
            >
              {paused ? "继续" : "暂停"}
            </button>
            <button
              className="explore-control"
              aria-pressed={exploring}
              onClick={() => {
                setExploring(!exploring);
                sceneAPI.current?.explore(!exploring);
              }}
            >
              <Maximize2 size={14} />
              {exploring ? "退出探索" : "拖动探索"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
