# Raspberry Pi

Use Raspberry Pi OS Lite 64-bit on a Pi 4 or newer, install Docker Engine, and confirm `uname -m` reports `aarch64`. The installer rejects 32-bit systems.

Choose the Raspberry Pi preset: one concurrent job, conservative ffmpeg threads, and bounded temporary storage. Put `/data` and `/work` on storage with adequate write endurance and free space. Video remuxing is usually light; WAV extraction is larger and more CPU/disk intensive. Avoid automatic video transcoding.

Run the wizard over SSH. Textual supports keyboard-only operation. A residential connection is materially more reliable than moving the same Pi workload to a datacenter VPS.
