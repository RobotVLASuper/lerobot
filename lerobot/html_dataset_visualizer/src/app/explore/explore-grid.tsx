"use client";

import React, { useRef } from "react";

type ExploreGridProps = {
  datasets: Array<{ id: string; videoUrl: string | null }>;
};

export default function ExploreGrid({ datasets }: ExploreGridProps) {
  // Create an array of refs for each video
  const videoRefs = useRef<(HTMLVideoElement | null)[]>([]);

  return (
    <main className="p-8">
      <h1 className="text-2xl font-bold mb-6">Explore LeRobot Datasets</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
        {datasets.map((ds, idx) => (
          <div
            key={ds.id}
            className="relative border rounded-lg p-4 bg-white shadow hover:shadow-lg transition overflow-hidden h-48 flex items-end group"
            onMouseEnter={() => {
              const vid = videoRefs.current[idx];
              if (vid) vid.play();
            }}
            onMouseLeave={() => {
              const vid = videoRefs.current[idx];
              if (vid) {
                vid.pause();
                vid.currentTime = 0;
              }
            }}
          >
            <video
              ref={(el) => {
                videoRefs.current[idx] = el;
              }}
              src={ds.videoUrl || undefined}
              className="absolute top-0 left-0 w-full h-full object-cover object-center z-0"
              loop
              muted
              playsInline
              preload="metadata"
              onTimeUpdate={(e) => {
                const vid = e.currentTarget;
                if (vid.currentTime >= 15) {
                  vid.pause();
                  vid.currentTime = 0;
                }
              }}
            />
            <div className="absolute top-0 left-0 w-full h-full bg-black/40 z-10 pointer-events-none" />
            <div className="relative z-20 font-mono text-blue-100 break-all text-sm bg-black/60 backdrop-blur px-2 py-1 rounded shadow">
              {ds.id}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
