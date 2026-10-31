"""
One-time setup and speed test for the AI painter (Stable Diffusion img2img).

    python setup_ai.py                 (or:  python setup_ai.py my_selfie.jpg)

It checks torch and your GPU, downloads the model the first time (about 2.3 GB, needs internet just once; after
that everything works offline), then repaints a photo once per look. It prints how long each took and saves
ai_test_<look>.jpg next to this file, so you can judge the result with your own eyes. If faces drift too far from
the photo, run the kiosk with AI_STRENGTH_SCALE=0.8; for bolder repaints use 1.2.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

INSTALL_HELP = """
Install the AI libraries first:
    pip install -r requirements.txt
    pip install torch --index-url https://download.pytorch.org/whl/cu124
(pick the right CUDA line for your driver on https://pytorch.org/get-started/locally/ )
"""
NO_CUDA_HELP = """
torch cannot see your NVIDIA GPU. The most common cause is that the CPU-only build of torch is installed.
Reinstall the CUDA build:
    pip uninstall -y torch
    pip install torch --index-url https://download.pytorch.org/whl/cu124
and make sure your NVIDIA driver is up to date.
"""


def main():
    from PIL import Image, ImageDraw

    print(f"Python {sys.version.split()[0]}")
    import ai_painter as ap

    if not ap.HAVE_LIBS:
        print("torch/diffusers are missing or failed to load:", ap.IMPORT_ERROR)
        print(INSTALL_HELP)
        return 1
    import torch
    print(f"torch {torch.__version__} (CUDA build: {torch.version.cuda})")
    if ap.DEVICE == "cuda":
        if not torch.cuda.is_available():
            print(NO_CUDA_HELP)
            return 1
        props = torch.cuda.get_device_properties(0)
        print(f"GPU: {props.name}, {props.total_memory / 2**30:.1f} GB")
    print(f"Model: {ap.MODEL_ID}" + (f" + {ap.LCM_LORA} (fast few-step sampling)" if ap.LCM_LORA else " (normal sampler, slower)"))

    print("\nLoading the model. The first run downloads about 2.3 GB, please wait...")
    started = time.time()
    try:
        ap._painter.ensure_loaded()
    except Exception as exc:
        print(f"\nCould not load the model: {exc}")
        print("Check your internet connection (needed once for the download) and try again.")
        return 1
    print(f"Loaded in {time.time() - started:.1f}s" +
          ("  (CPU offload is on: your GPU memory is tight, so photos will be slower)" if ap._painter.offloaded else ""))

    if len(sys.argv) > 1:
        img = Image.open(sys.argv[1]).convert("RGB")
    else:
        img = Image.new("RGB", (768, 768), (120, 150, 190))
        draw = ImageDraw.Draw(img)
        draw.ellipse([264, 170, 504, 470], fill=(224, 172, 140))
        draw.rectangle([200, 520, 568, 768], fill=(60, 90, 150))
        print("\n(No photo given, using a drawing. Run again with your own selfie to judge the quality:"
              " python setup_ai.py my_selfie.jpg)")

    print("\nRepainting one photo per look (the first, untimed pass warms up the GPU)...")
    ap.paint(img, "Anime")
    times = {}
    for theme in ("Anime", "Cats", "Sci-Fi", "Vintage"):
        started = time.time()
        out = ap.paint(img, theme)
        times[theme] = time.time() - started
        out.save(os.path.join(HERE, f"ai_test_{theme}.jpg"), quality=92)
        print(f"  {theme:8} {times[theme]:5.1f}s   -> ai_test_{theme}.jpg")

    worst = max(times.values())
    print()
    if worst <= 8:
        print(f"Fast ({worst:.1f}s at worst). You're good to go: python server.py")
    elif worst <= 20:
        print(f"Works ({worst:.1f}s at worst), within the 30 s target. python server.py")
    else:
        print(f"Slow ({worst:.1f}s at worst). Try AI_SIZE=448, close other apps that use the GPU, or leave AI_LCM_LORA at its default.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
