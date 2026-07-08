import { motion } from "framer-motion";
import { cn } from "@/lib/util";

/**
 * Ambient animated background — slow-drifting colour orbs behind a faint grid,
 * with a soft radial vignette. Purely decorative, GPU-friendly (transform/opacity),
 * and pointer-events-none so it never blocks interaction.
 */
export function Aurora({ className, dense = false }: { className?: string; dense?: boolean }) {
  return (
    <div className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}>
      {/* faint grid */}
      <div
        className="absolute inset-0 opacity-[0.5]"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(79,70,229,0.06) 1px, transparent 1px)," +
            "linear-gradient(to bottom, rgba(79,70,229,0.06) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
          maskImage: "radial-gradient(ellipse 80% 60% at 50% 30%, black 40%, transparent 100%)",
          WebkitMaskImage: "radial-gradient(ellipse 80% 60% at 50% 30%, black 40%, transparent 100%)",
        }}
      />

      {/* drifting orbs */}
      <Orb className="left-[8%] top-[-6%] h-[460px] w-[460px] bg-brand-300/40"
        x={[0, 60, -20, 0]} y={[0, 40, 10, 0]} s={[1, 1.15, 1.05, 1]} dur={22} />
      <Orb className="right-[4%] top-[6%] h-[380px] w-[380px] bg-teal-300/35"
        x={[0, -50, 20, 0]} y={[0, 30, -20, 0]} s={[1, 1.1, 0.95, 1]} dur={26} />
      <Orb className="left-[38%] top-[28%] h-[420px] w-[420px] bg-violet-300/30"
        x={[0, 40, -30, 0]} y={[0, -30, 20, 0]} s={[1, 1.2, 1, 1]} dur={30} />
      {dense && (
        <Orb className="right-[26%] bottom-[-10%] h-[360px] w-[360px] bg-sky-300/30"
          x={[0, -30, 40, 0]} y={[0, -20, 10, 0]} s={[1, 1.1, 1.05, 1]} dur={24} />
      )}
    </div>
  );
}

function Orb({ className, x, y, s, dur }: {
  className?: string; x: number[]; y: number[]; s: number[]; dur: number;
}) {
  return (
    <motion.div
      aria-hidden
      className={cn("absolute rounded-full blur-3xl", className)}
      animate={{ x, y, scale: s }}
      transition={{ duration: dur, repeat: Infinity, ease: "easeInOut" }}
    />
  );
}
