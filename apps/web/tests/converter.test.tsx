import { describe, expect, it } from "vitest"

import { parseDraft } from "@/components/converter-workbench"

describe("conversion draft parser", () => {
  it("parses mixed formats, qualities, and defaults", () => {
    const parsed = parseDraft(
      [
        "https://youtu.be/dQw4w9WgXcQ mp3 320k",
        "https://www.youtube.com/watch?v=9bZkp7q19f0 wav 48khz",
        "https://youtube.com/watch?v=J---aiyznGQ",
      ].join("\n"),
      "mp4",
      "1080p"
    )
    expect(parsed).toEqual([
      { url: "https://youtu.be/dQw4w9WgXcQ", format: "mp3", quality: "320k" },
      {
        url: "https://www.youtube.com/watch?v=9bZkp7q19f0",
        format: "wav",
        quality: "48khz",
      },
      {
        url: "https://youtube.com/watch?v=J---aiyznGQ",
        format: "mp4",
        quality: "1080p",
      },
    ])
  })

  it("collapses exact duplicate requests", () => {
    const parsed = parseDraft(
      "https://youtu.be/dQw4w9WgXcQ mp4 720p\nhttps://youtu.be/dQw4w9WgXcQ mp4 720p",
      "mp4",
      "720p"
    )
    expect(parsed).toHaveLength(1)
  })
})
