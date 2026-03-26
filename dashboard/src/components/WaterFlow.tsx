"use client";

import { useEffect, useRef, useCallback } from "react";
import { useTheme } from "@/lib/theme";

/**
 * Full-screen realistic turbulent water flow animation using Canvas.
 * Renders behind dashboard content as a fixed background.
 */
export function WaterFlow({ forceDark = false }: { forceDark?: boolean } = {}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);
  const { theme } = useTheme();
  const themeRef = useRef(forceDark ? "dark" : theme);
  if (!forceDark) themeRef.current = theme;
  else themeRef.current = "dark";

  const animate = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;

    /* ----- wave layer config ----- */
    interface WaveLayer {
      amplitude: number;
      wavelength: number;
      speed: number;
      phase: number;
      yOffset: number;
      alpha: number;
    }

    const layers: WaveLayer[] = [
      { amplitude: 40, wavelength: 300, speed: 0.015, phase: 0, yOffset: 0.30, alpha: 0.18 },
      { amplitude: 30, wavelength: 220, speed: 0.022, phase: 1.2, yOffset: 0.40, alpha: 0.15 },
      { amplitude: 50, wavelength: 400, speed: 0.010, phase: 2.5, yOffset: 0.50, alpha: 0.20 },
      { amplitude: 25, wavelength: 180, speed: 0.028, phase: 0.8, yOffset: 0.55, alpha: 0.12 },
      { amplitude: 35, wavelength: 260, speed: 0.018, phase: 3.7, yOffset: 0.65, alpha: 0.16 },
      { amplitude: 20, wavelength: 150, speed: 0.032, phase: 1.9, yOffset: 0.75, alpha: 0.10 },
    ];

    /* ----- foam / ripple particles ----- */
    interface Foam {
      x: number;
      y: number;
      r: number;
      vx: number;
      vy: number;
      life: number;
      maxLife: number;
    }

    const foamCount = Math.floor((W * H) / 8000);
    const foams: Foam[] = [];
    for (let i = 0; i < foamCount; i++) {
      foams.push({
        x: Math.random() * W,
        y: Math.random() * H,
        r: 1 + Math.random() * 2.5,
        vx: 0.3 + Math.random() * 1.2,
        vy: -0.2 + Math.random() * 0.4,
        life: Math.random() * 200,
        maxLife: 150 + Math.random() * 200,
      });
    }

    let t = 0;

    function draw() {
      t++;
      const dark = themeRef.current === "dark";

      /* background gradient */
      const bg = ctx!.createLinearGradient(0, 0, 0, H);
      if (dark) {
        bg.addColorStop(0, "#080e2a");
        bg.addColorStop(0.4, "#0c1840");
        bg.addColorStop(0.7, "#102058");
        bg.addColorStop(1, "#0a1540");
      } else {
        bg.addColorStop(0, "#c8ddf5");
        bg.addColorStop(0.3, "#a8c8ee");
        bg.addColorStop(0.6, "#88b5e5");
        bg.addColorStop(1, "#6a9fd8");
      }
      ctx!.fillStyle = bg;
      ctx!.fillRect(0, 0, W, H);

      /* draw wave layers */
      for (const layer of layers) {
        ctx!.beginPath();
        const baseY = H * layer.yOffset;
        ctx!.moveTo(0, H);

        for (let x = 0; x <= W; x += 3) {
          const y =
            baseY +
            Math.sin((x / layer.wavelength) * Math.PI * 2 + t * layer.speed + layer.phase) *
              layer.amplitude +
            Math.sin((x / (layer.wavelength * 0.6)) * Math.PI * 2 + t * layer.speed * 1.3 + layer.phase * 0.7) *
              (layer.amplitude * 0.4) +
            Math.sin((x / (layer.wavelength * 1.8)) * Math.PI * 2 - t * layer.speed * 0.7 + layer.phase * 1.5) *
              (layer.amplitude * 0.25);
          ctx!.lineTo(x, y);
        }

        ctx!.lineTo(W, H);
        ctx!.closePath();

        const grad = ctx!.createLinearGradient(0, baseY - layer.amplitude, 0, H);
        if (dark) {
          grad.addColorStop(0, `rgba(50, 110, 220, ${layer.alpha * 1.3})`);
          grad.addColorStop(0.5, `rgba(30, 80, 190, ${layer.alpha})`);
          grad.addColorStop(1, `rgba(15, 50, 140, ${layer.alpha * 0.7})`);
        } else {
          grad.addColorStop(0, `rgba(50, 100, 190, ${layer.alpha * 1.1})`);
          grad.addColorStop(0.5, `rgba(35, 80, 170, ${layer.alpha * 0.9})`);
          grad.addColorStop(1, `rgba(25, 65, 150, ${layer.alpha * 0.7})`);
        }
        ctx!.fillStyle = grad;
        ctx!.fill();
      }

      /* caustic light patterns */
      for (let i = 0; i < 5; i++) {
        const cx = ((Math.sin(t * 0.008 + i * 1.8) + 1) / 2) * W;
        const cy = ((Math.cos(t * 0.006 + i * 2.3) + 1) / 2) * H;
        const cr = 60 + Math.sin(t * 0.015 + i) * 30;
        const cg = ctx!.createRadialGradient(cx, cy, 0, cx, cy, cr);
        if (dark) {
          cg.addColorStop(0, "rgba(90, 170, 255, 0.12)");
          cg.addColorStop(1, "rgba(90, 170, 255, 0)");
        } else {
          cg.addColorStop(0, "rgba(255, 255, 255, 0.15)");
          cg.addColorStop(1, "rgba(255, 255, 255, 0)");
        }
        ctx!.fillStyle = cg;
        ctx!.fillRect(cx - cr, cy - cr, cr * 2, cr * 2);
      }

      /* foam particles */
      for (const f of foams) {
        f.x += f.vx + Math.sin(t * 0.02 + f.y * 0.01) * 0.5;
        f.y += f.vy + Math.cos(t * 0.015 + f.x * 0.008) * 0.3;
        f.life++;

        if (f.x > W + 10 || f.life > f.maxLife) {
          f.x = -5;
          f.y = Math.random() * H;
          f.life = 0;
        }

        const fadeIn = Math.min(f.life / 30, 1);
        const fadeOut = Math.max(1 - (f.life - f.maxLife + 40) / 40, 0);
        const opacity = fadeIn * fadeOut * (dark ? 0.3 : 0.5);

        ctx!.beginPath();
        ctx!.arc(f.x, f.y, f.r, 0, Math.PI * 2);
        ctx!.fillStyle = dark
          ? `rgba(150, 200, 255, ${opacity})`
          : `rgba(255, 255, 255, ${opacity})`;
        ctx!.fill();
      }

      /* surface shimmer lines */
      ctx!.save();
      ctx!.globalAlpha = dark ? 0.04 : 0.08;
      ctx!.strokeStyle = dark ? "#6090d0" : "#ffffff";
      ctx!.lineWidth = 1;
      for (let i = 0; i < 8; i++) {
        ctx!.beginPath();
        const baseY2 = H * (0.25 + i * 0.08);
        for (let x = 0; x <= W; x += 4) {
          const y =
            baseY2 +
            Math.sin(x * 0.008 + t * 0.02 + i * 0.9) * 15 +
            Math.sin(x * 0.015 - t * 0.012 + i * 1.5) * 8;
          if (x === 0) ctx!.moveTo(x, y);
          else ctx!.lineTo(x, y);
        }
        ctx!.stroke();
      }
      ctx!.restore();

      animFrameRef.current = requestAnimationFrame(draw);
    }

    draw();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    function resize() {
      if (!canvas) return;
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }

    resize();
    window.addEventListener("resize", resize);
    animate();

    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(animFrameRef.current);
    };
  }, [animate]);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none"
      style={{ zIndex: 0 }}
    />
  );
}
