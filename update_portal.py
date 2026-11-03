import os
import sys
import requests
import re
import json
import time
from urllib.parse import quote

m3u_content = "#EXTM3U\n"
total_all_channels = 0

if not os.path.exists('Portal.txt'):
    print("Error: File Portal.txt tidak ditemukan!")
    sys.exit(1)

with open('Portal.txt', 'r', encoding='utf-8') as f:
    lines = [line.strip() for line in f if line.strip()]

if not lines:
    print("Error: File Portal.txt kosong!")
    sys.exit(1)

print(f"Membaca {len(lines)} akun MAC Portal dari file...")

# Fungsi Helper Penembus Error 503 dengan Sistem Jeda (Auto-Retry)
def safe_request(url, headers, timeout=15, retries=3, delay=3):
    for i in range(retries):
        try:
            res = requests.get(url, headers=headers, timeout=timeout)
            if res.status_code == 200:
                return res
            elif res.status_code == 503:
                print(f"    [!] Server Error 503 (Sibuk). Mencoba kembali dalam {delay} detik... ({i+1}/{retries})")
                time.sleep(delay)
        except Exception:
            time.sleep(delay)
    return None

for index, account in enumerate(lines, start=1):
    if '|' not in account:
        print(f"Skipping baris {index}: Format salah (Gunakan URL|MAC)")
        continue
        
    PORTAL_URL, MAC_ADDRESS = account.split('|', 1)
    PORTAL_URL = PORTAL_URL.strip()
    MAC_ADDRESS = MAC_ADDRESS.strip()
    
    print(f"\n[{index}/{len(lines)}] Memproses: {PORTAL_URL}")
    
    # 1. Ambil domain murni string (Menjaga port :80 tetap aman)
    if '/c/' in PORTAL_URL:
        internal_url = PORTAL_URL.split('/c/')[0].rstrip('/')
    else:
        internal_url = PORTAL_URL.rstrip('/')
        
    api_url = f"{internal_url}/server/load.php"
    
    # Normalisasi skema TLS: Port 80 dikunci ke http demi menghindari kegagalan jabat tangan paket
    domain_clean = internal_url.replace("https://", "").replace("http://", "")
    if ":80" in domain_clean or "nxtbox.uk" in domain_clean.lower():
        if ":80" not in domain_clean:
            domain_clean = f"{domain_clean}:80"
        final_base_stream_url = f"http://{domain_clean}"
    else:
        final_base_stream_url = f"https://{domain_clean}" if "https" in PORTAL_URL else f"http://{domain_clean}"
            
    # Identitas perangkat keras tiruan lengkap untuk menembus proteksi token
    fake_stbid  = "00000000000000000000000000000000"
    user_agent = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stalker/"
    
    headers = {
        "User-Agent": user_agent,
        "Cookie": f"mac={MAC_ADDRESS}; stb_lang=en; timezone=Europe%2FParis; stbid={fake_stbid};",
        "Referer": f"{internal_url}/c/",
        "Accept": "*/*",
        "Connection": "keep-alive"
    }

    try:
        # 2. Langkah Handshake Resmi untuk Mengamankan Token Sesi Aktif
        handshake_url = f"{api_url}?type=stb&action=handshake&token=&stbid={fake_stbid}"
        response = safe_request(handshake_url, headers, timeout=12)
        token = ""
        
        if response and response.status_code == 200:
            try:
                token = response.json().get('js', {}).get('token', '')
                if token:
                    headers['Authorization'] = f"Bearer {token}"
                    print(f"-> Autentikasi Berhasil! Token Sesi Aktif: {token[:8]}...")
            except Exception:
                pass

        if not token:
            print("-> Peringatan: Gagal mendapatkan token dinamis. Mencoba menggunakan rute standar...")

        # 3. Tarik Kamus Kategori (Genre)
        genres_url = f"{api_url}?type=itv&action=get_genres"
        genre_mapping = {}
        genres_res = safe_request(genres_url, headers, timeout=10)
        if genres_res and genres_res.status_code == 200:
            try:
                genres_data = genres_res.json().get('js', [])
                if isinstance(genres_data, list):
                    for genre in genres_data:
                        if isinstance(genre, dict) and 'id' in genre and 'title' in genre:
                            genre_mapping[str(genre['id'])] = str(genre['title']).strip()
            except Exception:
                pass

        # 4. Tarik Data Utama Saluran TV
        channels_url = f"{api_url}?type=itv&action=get_all_channels"
        res = safe_request(channels_url, headers, timeout=18)
        if not res:
            print("-> Gagal mengambil siaran dari portal ini.")
            continue
            
        raw_text = res.text
        count = 0

        try:
            data = json.loads(raw_text)
            channels_list = []
            if isinstance(data, dict):
                js_content = data.get('js', [])
                if isinstance(js_content, dict) and 'data' in js_content:
                    channels_list = js_content.get('data', [])
                elif isinstance(js_content, dict):
                    channels_list = list(js_content.values())
                elif isinstance(js_content, list):
                    channels_list = js_content
            
            if isinstance(channels_list, list) and len(channels_list) > 0:
                for ch in channels_list:
                    if not isinstance(ch, dict):
                        continue
                        
                    name = ch.get('name', 'Unknown Channel').strip()
                    cmd = ch.get('cmd', '')
                    ch_id = str(ch.get('id', '')).strip()
                    logo = ch.get('logo', '')
                    
                    # Filter Konten VOD / Movie
                    if str(ch.get('is_vodi', '0')) == '1':
                        continue
                    if any(x in str(cmd).lower() for x in ['kinopoisk:', 'vclub:', 'pvr:', 'movie:']):
                        continue
                    
                    # Pengelompokan Kategori Grup
                    category_id = str(ch.get('category_id', ''))
                    ch_group = genre_mapping.get(category_id, ch.get('tv_genre_name', '').strip())
                        
                    if not ch_group or ch_group == f'Portal_{index}' or ch_group == 'Lainnya':
                        try:
                            clean_name_for_match = re.sub(r'[\(\)\[\]]', ' ', name).split()
                            if clean_name_for_match and len(clean_name_for_match) >= 1:
                                first_word = clean_name_for_match[0].upper()
                                ch_group = f"{first_word} - Live TV" if len(first_word) <= 4 else "Live TV General"
                            else:
                                ch_group = "Live TV General"
                        except Exception:
                            ch_group = "Live TV General"
                    
                    if any(keyword in ch_group.lower() for keyword in ['vod', 'movie', 'cinema', 'film', 'series']):
                        continue

                    # 5. RESOLUSI EKSTRAKSI ID STREAM
                    clean_cmd = str(cmd).replace('\\', '').strip()
                    stream_id = clean_cmd.split('/')[-1].replace('"', '').replace("'", "").replace('_', '').strip()
                    
                    if not stream_id or len(stream_id) > 10 or not stream_id.isdigit():
                        stream_id = ch_id
                    
                    # ========================================================
                    # KUNCI UTAMA SAKTI: PENYUNTIKKAN TOKEN DINAMIS KE URL STREAM
                    # ========================================================
                    if token:
                        # Melampirkan parameter token sesi aktif hasil handshake ke URL putar
                        stream_url = f"{final_base_stream_url}/play/live.php?mac={MAC_ADDRESS}&stream={stream_id}&extension=ts&token={token}"
                    else:
                        stream_url = f"{final_base_stream_url}/play/live.php?mac={MAC_ADDRESS}&stream={stream_id}&extension=ts"
                    
                    # URL Gambar Logo
                    logo_url = ""
                    if logo:
                        logo_str = str(logo).strip()
                        logo_url = logo_str if logo_str.startswith('http') else f"{final_base_stream_url}/misc/logos/320/{logo_str.lstrip('/')}"
                        if not any(logo_url.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif']):
                            logo_url += '.png'
                    else:
                        encoded_name = quote(name)
                        logo_url = f"https://ui-avatars.com{encoded_name}&background=random&color=fff&size=256"
                    
                    safe_name = name.replace('"', "'")
                    safe_group = ch_group.replace('"', "'")
                    
                    # Kompilasi Metadata M3U
                    m3u_content += f'#EXTINF:-1 tvg-id="{ch_id}" tvg-name="{safe_name}" tvg-logo="{logo_url}" group-title="{safe_group}",{name}\n'
                    m3u_content += f'#EXTVLCOPT:http-user-agent={user_agent}\n'
                    m3u_content += f'#EXTVLCOPT:http-cookie=mac={MAC_ADDRESS}; stbid={fake_stbid};\n'
                    m3u_content += f'{stream_url}\n'
                    count += 1
        except Exception as json_err:
            print(f"-> Gagal memproses data JSON: {json_err}")

        print(f"-> Sukses mengekstrak {count} Live TV channel.")
        total_all_channels += count

    except Exception as e:
        print(f"-> Gagal memproses portal karena: {e}")
        continue

# Simpan hasil akhir ke berkas playlist.m3u
with open('playlist.m3u', 'w', encoding='utf-8') as f:
    f.write(m3u_content)

print(f"\nSelesai! Berhasil membuat 'playlist.m3u' dengan suntikan Token Sesi Aktif.")
