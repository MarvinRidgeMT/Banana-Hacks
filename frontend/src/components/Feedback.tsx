import type { ReactNode } from "react";

/** A failed load: one sentence and a way to retry. */
export function ErrorNote({ message, onRetry, className = "" }: { message: string; onRetry: () => void; className?: string }) {
  return (
    <div role="alert" className={`flex flex-wrap items-center gap-x-5 gap-y-3 ${className}`}>
      <p className="text-invented">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-sm border border-ink px-4 py-2 font-semibold hover:bg-tag"
      >
        Try again
      </button>
    </div>
  );
}

/** A grey placeholder bar or block. Pulses unless reduced motion is on. */
export function Bone({ className = "" }: { className?: string }) {
  return <span aria-hidden className={`block animate-pulse rounded-sm bg-line ${className}`} />;
}

/** A dark exhibit frame in the photo's place, with an optional status line. */
export function PhotoSkeleton({ children, className = "" }: { children?: ReactNode; className?: string }) {
  return (
    <div className={`exhibit-frame relative mx-auto grid aspect-[4/5] w-full max-w-[57.6vh] place-items-center ${className}`}>
      <span aria-hidden className="absolute inset-0 animate-pulse bg-ground/5" />
      {children && <p className="relative max-w-xs px-6 text-center text-lg text-ground" aria-live="polite">{children}</p>}
    </div>
  );
}

/** The Real / Rebuilt / Invented bar and its three rows, before the numbers arrive. */
export function LegendSkeleton() {
  return (
    <div aria-hidden>
      <Bone className="h-9 w-full" />
      <div className="mt-3 space-y-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex items-center gap-3">
            <Bone className="h-4 w-4" />
            <Bone className="h-4 w-20" />
            <Bone className="ml-auto h-5 w-10" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** A demo card before /demos answers. */
export function DemoCardSkeleton() {
  return (
    <div aria-hidden>
      <div className="exhibit-frame aspect-[4/5] w-full">
        <span className="block h-full w-full animate-pulse bg-ground/5" />
      </div>
      <Bone className="mt-6 h-6 w-3/4" />
      <Bone className="mt-3 h-4 w-full" />
    </div>
  );
}
