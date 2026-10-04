import React from 'react';

// MeghSync logo (public/meghsync-logo.png). It has its own light background, so it is shown as a rounded tile
// that looks right on both the white public header and the dark command-center header.
export default function BrandLogo({ className = 'w-8 h-8' }: { className?: string }) {
  return <img src="/meghsync-logo.png" alt="MeghSync" className={`${className} rounded-lg object-cover shrink-0`} />;
}
