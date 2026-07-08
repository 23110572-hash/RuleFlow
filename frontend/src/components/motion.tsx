import { ReactNode } from "react";
import { motion, HTMLMotionProps } from "framer-motion";
import { cn } from "@/lib/util";

/** Button with tactile press feedback (scale on tap) — the "haptic" feel. */
export function TButton({
  children, className, variant = "primary", ...props
}: HTMLMotionProps<"button"> & { variant?: "primary" | "ghost" | "dark" }) {
  const styles = {
    primary: "bg-brand-600 text-white hover:bg-brand-700 shadow-soft",
    ghost: "bg-white border border-ink-200 text-ink-700 hover:bg-ink-50",
    dark: "bg-ink-900 text-white hover:bg-ink-800",
  }[variant];
  return (
    <motion.button
      whileTap={{ scale: 0.96 }}
      whileHover={{ y: -1 }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2",
        "disabled:opacity-50 disabled:pointer-events-none",
        styles, className
      )}
      {...props}
    >
      {children}
    </motion.button>
  );
}

/** Fade/slide-in wrapper for page content. */
export function PageMotion({ children }: { children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

export function FadeIn({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
