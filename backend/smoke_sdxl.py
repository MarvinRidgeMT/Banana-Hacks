import sys, time, torch
from PIL import Image, ImageDraw
from diffusers import StableDiffusionXLInpaintPipeline, AutoencoderKL

DEV = "mps"
MODEL = "diffusers/stable-diffusion-xl-1.0-inpainting-0.1"

vae = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=torch.float16)
try:
    pipe = StableDiffusionXLInpaintPipeline.from_pretrained(MODEL, vae=vae, torch_dtype=torch.float16, variant="fp16")
except Exception:
    pipe = StableDiffusionXLInpaintPipeline.from_pretrained(MODEL, vae=vae, torch_dtype=torch.float16)
pipe = pipe.to(DEV)
pipe.enable_attention_slicing()

# Use a real photo if you pass one, otherwise a simple test image
if len(sys.argv) > 1:
    img = Image.open(sys.argv[1]).convert("RGB").resize((1024, 1024))
else:
    img = Image.new("RGB", (1024, 1024), (140, 140, 140))
    d = ImageDraw.Draw(img)
    d.ellipse((312, 212, 712, 712), fill=(90, 90, 90))
    d.rectangle((0, 760, 1024, 1024), fill=(60, 60, 60))

# The "damaged" area to fill in: a box in the middle
mask = Image.new("L", (1024, 1024), 0)
ImageDraw.Draw(mask).rectangle((362, 412, 662, 612), fill=255)

prompt = "old black and white photograph, film grain, natural lighting"
neg = "modern, color, cartoon, painting"

print("Warming up...")
pipe(prompt=prompt, negative_prompt=neg, image=img, mask_image=mask, num_inference_steps=2)

print("Timing one seed...")
t = time.time()
out = pipe(prompt=prompt, negative_prompt=neg, image=img, mask_image=mask,
           num_inference_steps=20, guidance_scale=6.0, strength=0.99,
           generator=torch.Generator("cpu").manual_seed(11)).images[0]
print(f"One seed, 20 steps, 1024 px: {time.time() - t:.1f} s")
out.save("smoke_out.png")
print("Saved smoke_out.png")
