import React from "react";
import ExploreGrid from "./explore-grid";
import {
  DatasetMetadata,
  fetchJson,
  formatStringWithVars,
} from "@/utils/parquetUtils";

// Server component for data fetching
export default async function ExplorePage() {
  let datasets: any[] = [];
  try {
    const res = await fetch(
      "https://huggingface.co/api/datasets?filter=lerobot&sort=lastModified",
      {
        cache: "no-store",
      },
    );
    if (!res.ok) throw new Error("Failed to fetch datasets");
    datasets = await res.json();
  } catch (e) {
    return <div className="p-8 text-red-600">Failed to load datasets.</div>;
  }

  // Fetch episode 0 data for each dataset
  const datasetWithVideos = (
    await Promise.all(
      datasets.map(async (ds: any) => {
        try {
          const [org, dataset] = ds.id.split("/");
          const repoId = `${org}/${dataset}`;
          const jsonUrl = `https://huggingface.co/datasets/${repoId}/resolve/main/meta/info.json`;
          const info = await fetchJson<DatasetMetadata>(jsonUrl);
          const videoEntry = Object.entries(info.features).find(
            ([_key, value]) => value.dtype === "video",
          );
          let videoUrl: string | null = null;
          if (videoEntry) {
            const [key] = videoEntry;
            const videoPath = formatStringWithVars(info.video_path, {
              video_key: key,
              episode_chunk: "0".padStart(3, "0"),
              episode_index: "0".padStart(6, "0"),
            });
            videoUrl =
              `https://huggingface.co/datasets/${repoId}/resolve/main/` +
              videoPath;
          }
          return { id: repoId, videoUrl };
        } catch (err) {
          console.error(
            `Failed to fetch or parse dataset info for ${ds.id}:`,
            err,
          );
          return null;
        }
      }),
    )
  ).filter(Boolean);

  return <ExploreGrid datasets={datasetWithVideos} />;
}
