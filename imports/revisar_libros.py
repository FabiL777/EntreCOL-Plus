
import json
from pathlib import Path

ruta = Path(__file__).resolve().parents[1] / "data" / "Books.json"

ids_revisar = {12224, 16914, 22128, 34889}

with ruta.open("r", encoding="utf-8-sig") as archivo:
    libros = json.load(archivo)

for libro in libros:
    if int(libro["bookID"]) in ids_revisar:
        print("\n" + "=" * 60)
        print(f"LIBRO {libro['bookID']}")
        print("=" * 60)

        for campo, valor in libro.items():
            print(f"{campo}: {valor}")
