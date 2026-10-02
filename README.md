# Python Package Downloader

Download semua package Python dari sebuah `requirements.txt` (beserta seluruh dependency-nya) untuk **install offline**, pakai GitHub Actions sebagai agent. Prinsipnya sama seperti `locust-offline-downloader`, tapi untuk requirements apa pun, dan ada UI web untuk copas `requirements.txt`.

Workflow berjalan **di OS target yang sebenarnya** (Windows / Linux / macOS), jadi pip me-resolve dependency khusus platform secara native. Lalu workflow mengecek dengan `pip install --no-index --dry-run`, jadi bundle dijamin bisa di-install tanpa internet.

## Isi artifact

```
packages/                 semua file .whl
requirements.txt          versi ter-pin dari semua isi packages/
requirements.input.txt    requirements asli yang diminta
```

Install di mesin offline:

```bash
pip install --no-index --find-links=packages -r requirements.txt
```

## Setup (sekali saja)

1. Buat repo di GitHub (mis. `badrusalam11/python-package-downloader`) lalu push:
   ```bash
   git remote add origin https://github.com/badrusalam11/python-package-downloader.git
   git push -u origin main
   ```
2. **Aktifkan GitHub Pages untuk UI**: Settings → Pages → Source: *Deploy from a branch* → `main` / `/docs`.
   UI akan ada di `https://badrusalam11.github.io/python-package-downloader/`.
   (Bisa juga buka `docs/index.html` langsung dari disk.)
3. **Buat token**: [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new), *Repository access* → hanya repo ini, *Permissions* → **Actions: Read and write**.

## Cara pakai

### Lewat UI web

1. Buka UI-nya, isi repository + token di ⚙️ (sekali saja; centang *Remember* kalau mau token disimpan di browser).
2. Paste `requirements.txt` (atau drag & drop file-nya).
3. Pilih versi Python, mode, dan satu atau lebih OS target. Setiap OS jadi satu workflow run.
4. Klik **Download packages**. Status run muncul di panel kanan, dan tombol download artifact muncul begitu run selesai.

> Link download artifact mengarah ke github.com, jadi browser harus sudah login ke GitHub.

### Lewat GitHub langsung

Actions → **Download Python Packages** → *Run workflow*. Field `requirements` di form GitHub cuma satu baris, jadi pisahkan package dengan spasi:

```
requests==2.32.3 flask>=3 pandas
```

### Lewat API / curl

```bash
curl -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/badrusalam11/python-package-downloader/actions/workflows/download.yml/dispatches \
  -d "$(jq -n --rawfile r requirements.txt \
        '{ref:"main", inputs:{requirements:$r, python_version:"3.12", target_os:"linux-x64", mode:"wheels-only"}}')"
```

## Opsi

| Input | Pilihan | Keterangan |
|-------|---------|------------|
| `python_version` | 3.10 – 3.14 | Harus sama dengan versi Python di mesin offline |
| `target_os` | `windows-x64`, `linux-x64`, `linux-arm64`, `macos-arm64` | Runner: `windows-latest`, `ubuntu-latest`, `ubuntu-24.04-arm`, `macos-latest` |
| `mode` | `wheels-only` | Hanya binary wheel (`pip download --only-binary=:all:`), sama seperti locust-offline-downloader |
| | `build-sdists` | Package yang tidak punya wheel di-build dari source di runner (`pip wheel`), hasilnya tetap berupa wheel |

## Catatan

- Wheel Linux di-build/di-resolve di Ubuntu terbaru. Wheel `manylinux` umumnya jalan di distro lain juga, tapi package yang di-build dari source (mode `build-sdists`) bisa butuh glibc yang sama atau lebih baru dari runner.
- Batas ukuran input `workflow_dispatch` sekitar 65 ribu karakter. Kalau requirements lebih besar dari itu, pecah jadi beberapa run.
- Artifact disimpan 30 hari.
- Test lokal: `REQUIREMENTS="requests flask" python scripts/bundle.py --out bundle`
