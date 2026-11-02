import os
import sys
import requests
import re
import json

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

for index, account in enumerate(lines, start=1):
    if '|' not in account:
        print(f"Skipping baris {index}: Format salah (Gunakan URL|MAC)")
        continue
        
    PORTAL_URL, MAC_ADDRESS = account.split('|', 1)
    PORTAL_URL = PORTAL_URL.strip()
    MAC_ADDRESS = MAC_ADDRESS.strip()
    
    print(f"\n[{index}/{len(lines)}] Memproses: {PORTAL_URL}")
    
    # PERBAIKAN UTAMA: Perbaikan ekstraksi Base URL agar menghasilkan String yang valid
    if '/c/' in PORTAL_URL:
        base_url = PORTAL_URL.split('/c/')[0].rstrip('/')
    else:
        base_url = PORTAL_URL.rstrip('/')
        
    api_url = f"{base_url}/server/load.php"
    
    user_agent = 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbid/000000000000000000000000000000000000'
    headers = {
        'User-Agent': user_agent,
        'Cookie': f'mac={MAC_ADDRESS}; stb_lang=en; timezone=Europe%2FParis;',
        'Referer': f"{base_url}/c/",
        'Accept': '*/*',
        'Connection': 'keep-alive'
    }
    
    try:
        # 1. Handshake Token
        handshake_url = f"{api_url}?type=stb&action=handshake&token="
        response = requests.get(handshake_url, headers=headers, timeout=12)
        token = ""
        
        if response.status_code == 200:
            try:
                token = response.json().get('js', {}).get('token', '')
                if token:
                    headers['Authorization'] = f"Bearer {token}"
                    print("-> Autentikasi Handshake Berhasil!")
            except Exception:
                pass

        # 2. Tarik Kamus Kategori
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
            pass

        # 3. Tarik Data Saluran
        channels_url = f"{api_url}?type=itv&action=get_all_channels"
        res = requests.get(channels_url, headers=headers, timeout=15)
        raw_text = res.text
        count = 0

        # METODE 1: Parsing JSON
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
                    
                    # Filter Konten VOD / Movie
                    if str(ch.get('is_vodi', '0')) == '1':
                        continue
                    if any(x in str(cmd).lower() for x in ['kinopoisk:', 'vclub:', 'pvr:', 'movie:']):
                        continue
                    
                    category_id = str(ch.get('category_id', ''))
                    ch_group = genre_mapping.get(category_id, ch.get('tv_genre_name', '').strip() or f'Portal_{index}')
                    
                    if any(keyword in ch_group.lower() for keyword in ['vod', 'movie', 'cinema', 'film', 'series']):
                        continue

                    # --- BLOK RE-WRITE STRUKTUR URL MANDATORI ---
                    clean_cmd = str(cmd).replace('\\', '').strip()
                    stream_id = clean_cmd.split('/')[-1].replace('"', '').replace("'", "").replace('_', '').strip()
                    
                    if not stream_id or len(stream_id) > 10:
                        stream_id = ch_id
                    
                    # PENGGANTIAN TOTAL: Memaksa tautan langsung menggunakan domain server Anda
                    if token:
                        stream_url = f"{base_url}/play/live.php?mac={MAC_ADDRESS}&stream={stream_id}&token={token}"
                    else:
                        stream_url = f"{base_url}/live/{MAC_ADDRESS}/555/{stream_id}.ts"
                    
                    # Normalisasi Logo
                    logo_url = ""
                    if logo:
                        logo_str = str(logo).strip()
                        if logo_str.startswith('http'):
                            logo_url = logo_str
                        else:
                            if not any(logo_str.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif']):
                                logo_str += '.png'
                            logo_url = f"{base_url}/misc/logos/320/{logo_str}"
                    
                    safe_name = name.replace('"', "'")
                    safe_group = ch_group.replace('"', "'")
                    
                    m3u_content += f'#EXTINF:-1 tvg-id="{ch_id}" tvg-name="{safe_name}" tvg-logo="{logo_url}" group-title="{safe_group}",{name}\n'
                    m3u_content += f'#EXTVLCOPT:http-user-agent={user_agent}\n'
                    m3u_content += f'#EXTVLCOPT:http-cookie=mac={MAC_ADDRESS}\n'
                    m3u_content += f'{stream_url}\n'
                    count += 1
        except Exception:
            pass

        # METODE FALLBACK 2: Regular Expression (Kini dilengkapi dengan pembersihan Localhost)
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
                        
                    clean_cmd = cmd.replace('\\', '').strip()
                    stream_id = clean_cmd.split('/')[-1].replace('"', '').replace("'", "").replace('_', '').strip()
                    
                    if not stream_id or len(stream_id) > 10:
                        stream_id = ch_id
                        
                    # Penerapan pembersihan localhost paksa pada jalur fallback
                    if token:
                        stream_url = f"{base_url}/play/live.php?mac={MAC_ADDRESS}&stream={stream_id}&token={token}"
                    else:
                        stream_url = f"{base_url}/live/{MAC_ADDRESS}/555/{stream_id}.ts"
                        
                    safe_name = name.replace('"', "'")
                    safe_group = ch_group.replace('"', "'")
                    
                    m3u_content += f'#EXTINF:-1 tvg-id="{ch_id}" tvg-name="{safe_name}" group-title="{safe_group}",{name}\n'
                    m3u_content += f'#EXTVLCOPT:http-user-agent={user_agent}\n'
                    m3u_content += f'#EXTVLCOPT:http-cookie=mac={MAC_ADDRESS}\n'
                    m3u_content += f'{stream_url}\n'
                    count += 1
                    
        print(f"-> Sukses mengekstrak {count} Live TV channel.")
        total_all_channels += count

    except Exception as e:
        print(f"-> Gagal memproses portal ini: {e}")
        continue

with open('mac_playlist.m3u', 'w', encoding='utf-8') as f:
    f.write(m3u_content)
print(f"\nSelesai! Hasil akhir bersih dari localhost telah disimpan ke 'mac_playlist.m3u'.")
