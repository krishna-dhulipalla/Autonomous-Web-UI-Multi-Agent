import io
from PIL import Image

def _compute_dhash(image_bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(img.getdata())
        print(f"Pixels: {pixels}")
        diff = []
        for row in range(8):
            for col in range(8):
                diff.append(pixels[row * 9 + col] > pixels[row * 9 + col + 1])
        return sum([1 << i for i, v in enumerate(diff) if v])
    except Exception as e:
        print(f"dHash failed: {e}")
        return 0

# Create a checkerboard image
img = Image.new('RGB', (100, 100), color = 'white')
pixels = img.load()
for i in range(100):
    for j in range(100):
        if (i // 10 + j // 10) % 2 == 0:
            pixels[i,j] = (0, 0, 0) # Black

img_byte_arr = io.BytesIO()
img.save(img_byte_arr, format='PNG')
img_bytes = img_byte_arr.getvalue()

hash1 = _compute_dhash(img_bytes)
print(f"Hash 1: {hash1}")

# Same image should have same hash
hash2 = _compute_dhash(img_bytes)
print(f"Hash 2: {hash2}")
assert hash1 == hash2

# Different image (inverse checkerboard)
img2 = Image.new('RGB', (100, 100), color = 'black')
pixels2 = img2.load()
for i in range(100):
    for j in range(100):
        if (i // 10 + j // 10) % 2 == 0:
            pixels2[i,j] = (255, 255, 255) # White

img_byte_arr2 = io.BytesIO()
img2.save(img_byte_arr2, format='PNG')
img_bytes2 = img_byte_arr2.getvalue()

hash3 = _compute_dhash(img_bytes2)
print(f"Hash 3: {hash3}")
assert hash1 != hash3

print("dHash verification passed!")
