import React from 'react';

// Small red counter bubble. Renders nothing when the count is 0, so it disappears by itself
// once the last pending report is approved or rejected.
export default function CountBadge({ count, className = '' }: { count: number; className?: string }) {
  if (!count || count < 1) return null;
  return (
    <span
      className={`inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold leading-none ${className}`}
      aria-label={`${count} pending`}
    >
      {count > 9 ? '9+' : count}
    </span>
  );
}
