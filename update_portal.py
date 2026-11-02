import os
import sys
import requests
import re
import json

m3u_content = "#EXTM3U\n"
total_all_channels = 0

# 1. Validasi File Input
if not os.path.exists('Portal.txt'):
    print("Error: File Portal.txt tidak ditemukan!")
    sys.exit(1)

with open('Portal.txt', 'r', encoding='utf-8') as f:
    lines = [line.strip() for line in f if line.strip()]

if not lines:
    print("Error: File Portal.txt kosong!")
    sys.exit(1)

print(f"Membaca {len(lines)} akun MAC Portal dari file...")

# 2. Iterasi Setiap Akun di Portal.txt
for index, account in enumerate(lines, start=1):
    if '|' not in account:
        print(f"Skipping baris {index}: Format salah (Gunakan URL|MAC)")
        continue
        
    PORTAL_URL, MAC_ADDRESS = account.split('|', 1)
    PORTAL_URL = PORTAL_URL.strip()
    MAC_ADDRESS = MAC_ADDRESS.strip()
    
    print(f"\n[{index}/{len(lines)}] Memproses: {PORTAL_URL}")
    
    # Normalisasi Base URL (Menghapus sub-direktori /c/ jika ada)
    if '/c/' in PORTAL_URL:
        base_url = PORTAL_URL.split('/c/')[0].rstrip('/')
    else:
        base_url = PORTAL_URL.rstrip('/')
        
    api_url = f"{base_url}/server/load.php"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbid/000000000000000000000000000000000000',
        'Cookie': f'mac={MAC_ADDRESS}; stb_lang=en; timezone=Europe%2FParis;',
        'Referer': f"{base_url}/c/",
        'Accept': '*/*',
        'Connection': 'keep-alive'
    }
    
    try:
        # A. Jabat Tangan / Handshake Token ke Server Stalker
        handshake_url = f"{api_url}?type=stb&action=handshake&token="
        response = requests.get(handshake_url, headers=headers, timeout=12)
        
        if response.status_code == 200:
            try:
                token = response.json().get('js', {}).get('token', '')
                if token:
                    headers['Authorization'] = f"Bearer {token}"
                    print("-> Autentikasi Handshake Berhasil!")
            except Exception:
                print("-> Gagal mengurai token handshake, mencoba melanjutkan...")

        # B. Tarik Kamus Genre/Kategori untuk Pemetaan Group-Title
        genres_url = f"{api_url}?type=itv&action=get_genres"
        genre_mapping = {}
        try:
            genres_res = requests.get(genres_url, headers=headers, timeout=10)
            genres_data = genres_res.json().get('js', [])
            if isinstance(genres_data, list):
                for genre in genres_data:
                    if isinstance(genre, dict) and 'id' in genre and 'title' in genre:
                        genre_mapping[str(genre['id'])] = str(genre['title']).strip()
        except Exception:
            print("-> Gagal mengambil daftar genre resmi, menggunakan nama grup mentah.")

        # C. Tarik Data Seluruh Saluran TV
        channels_url = f"{api_url}?type=itv&action=get_all_channels"
        res = requests.get(channels_url, headers=headers, timeout=15)
        raw_text = res.text
        count = 0

        # --- METODE 1: PARSING JSON RESMI ---
        try:
            data = json.loads(raw_text)
            channels_list = data.get('js', [])
            
            if isinstance(channels_list, dict):
                channels_list = list(channels_list.values())
                
            if isinstance(channels_list, list) and len(channels_list) > 0:
                for ch in channels_list:
                    if not isinstance(ch, dict):
                        continue
                        
                    name = ch.get('name', 'Unknown Channel').strip()
                    cmd = ch.get('cmd', '')
                    ch_id = str(ch.get('id', '')).strip()
                    logo = ch.get('logo', '')
                    
                    # 1. FILTER ELIMINASI VOD / MOVIE (Lewati film/serial)
                    if str(ch.get('is_vodi', '0')) == '1':
                        continue
                    if any(x in str(cmd).lower() for x in ['kinopoisk:', 'vclub:', 'pvr:', 'movie:', 'vclub_info:']):
                        continue
                    
                    # Penentuan Nama Kategori
                    category_id = str(ch.get('category_id', ''))
                    if category_id in genre_mapping:
                        ch_group = genre_mapping[category_id]
                    else:
                        ch_group = ch.get('tv_genre_name', '').strip() or f'Portal_{index}'
                    
                    vod_keywords = ['vod', 'movie', 'cinema', 'film', 'series', 'netflix', 'disney', 'hbo', 'sinema', 'box office']
                    if any(keyword in ch_group.lower() for keyword in vod_keywords):
                        continue

                    # 2. RESOLUSI STREAM URL (Konversi Localhost ke Direct Path External Player)
                    stream_url = ""
                    if cmd:
                        clean_cmd = str(cmd).replace('\\', '').strip()
                        link_match = re.search(r'(http[s]?://\S+)', clean_cmd)
                        
                        if link_match:
                            full_found_url = link_match.group(1).replace('"', '').replace("'", "")
                            if "localhost" in full_found_url:
                                stream_id = full_found_url.split('/')[-1].replace('_', '').strip()
                                stream_url = f"{base_url}/live/{MAC_ADDRESS}/555/{stream_id}.ts"
                            else:
                                stream_url = full_found_url
                        else:
                            stream_id = clean_cmd.split('/')[-1].replace('"', '').replace("'", "").replace('_', '').strip()
                            stream_url = f"{base_url}/live/{MAC_ADDRESS}/555/{stream_id}.ts"
                    
                    if not stream_url or "localhost" in stream_url:
                        stream_url = f"{base_url}/playlist/live/{ch_id}.ts"
                        
                    # 3. PENYUSUNAN URL LOGO SALURAN
                    logo_url = ""
                    if logo:
                        logo_str = str(logo).strip()
                        if logo_str.startswith('http'):
                            logo_url = logo_str
                        else:
                            if not any(logo_str.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif']):
                                logo_str += '.png'
                            logo_url = f"{base_url}/misc/logos/320/{logo_str}"
                    
                    # Pembersihan karakter kutip ganda agar tag M3U valid
                    safe_name = name.replace('"', "'")
                    safe_group = ch_group.replace('"', "'")
                    
                    # Gabungkan menjadi Baris Metadata Standar M3U
                    m3u_line = f'#EXTINF:-1 tvg-id="{ch_id}" tvg-name="{safe_name}"'
                    if logo_url:
                        m3u_line += f' tvg-logo="{logo_url}"'
                    m3u_line += f' group-title="{safe_group}",{name}\n{stream_url}\n'
                    
                    m3u_content += m3u_line
                    count += 1
        except Exception:
            pass  # Jika JSON gagal, lanjut ke metode fallback di bawah

        # --- METODE FALLBACK 2: REGULAR EXPRESSION (Cadangan jika JSON Corrupt) ---
        if count == 0:
            matches = re.findall(r'"id"\s*:\s*"([^"]+)"[^}]+?"name"\s*:\s*"([^"]+)"[^}]+?"cmd"\s*:\s*"([^"]+)"', raw_text)
            if matches:
                for ch_id, name, cmd in matches:
                    ch_id = ch_id.strip()
                    name = name.strip()
                    
                    if any(x in cmd.lower() for x in ['kinopoisk:', 'vclub:', 'movie:']):
                        continue
                        
                    genre_match = re.search(r'"tv_genre_name"\s*:\s*"([^"]+)"', raw_text)
                    ch_group = genre_match.group(1).strip() if genre_match else f'Portal_{index}'
                    
                    if any(keyword in ch_group.lower() for keyword in ['vod', 'movie', 'cinema', 'film', 'series']):
                        continue
                        
                    safe_name = name.replace('"', "'")
                    safe_group = ch_group.replace('"', "'")
                    
                    clean_cmd = cmd.replace('\\', '').strip()
                    link_match = re.search(r'(http[s]?://\S+)', clean_cmd)
                    if link_match:
                        full_found_url = link_match.group(1).replace('"', '').replace("'", "")
                        if "localhost" in full_found_url:
                            stream_id = full_found_url.split('/')[-1].replace('_', '').strip()
                            stream_url = f"{base_url}/live/{MAC_ADDRESS}/555/{stream_id}.ts"
                        else:
                            stream_url = full_found_url
                    else:
                        stream_id = clean_cmd.split('/')[-1].replace('"', '').replace("'", "").replace('_', '').strip()
                        stream_url = f"{base_url}/live/{MAC_ADDRESS}/555/{stream_id}.ts"
                        
                    m3u_content += f'#EXTINF:-1 tvg-id="{ch_id}" tvg-name="{safe_name}" group-title="{safe_group}",{name}\n{stream_url}\n'
                    count += 1
                    
        print(f"-> Sukses mengekstrak {count} Live TV channel (Konten VOD berhasil disaring keluar).")
        total_all_channels += count

    except Exception as e:
        print(f"-> Gagal memproses portal ini karena kendala jaringan: {e}")
        continue

# 3. Penyimpanan File Akhir
print(f"\nSelesai! Total keseluruhan: {total_all_channels} Live TV channel berhasil dikumpulkan.")

with open('mac_playlist.m3u', 'w', encoding='utf-8') as f:
    f.write(m3u_content)
