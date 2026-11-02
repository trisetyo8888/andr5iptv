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
    
    # Bersihkan /c/ di ujung URL untuk mendapatkan domain utama server
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

        # 3. Tarik Semua Data Saluran
        channels_url = f"{api_url}?type=itv&action=get_all_channels"
        res = requests.get(channels_url, headers=headers, timeout=15)
        raw_text = res.text
        count = 0

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
                    
                    # Filter Konten VOD/Movie
                    if str(ch.get('is_vodi', '0')) == '1':
                        continue
                    if any(x in str(cmd).lower() for x in ['kinopoisk:', 'vclub:', 'pvr:', 'movie:']):
                        continue
                    
                    category_id = str(ch.get('category_id', ''))
                    ch_group = genre_mapping.get(category_id, ch.get('tv_genre_name', '').strip() or f'Portal_{index}')
                    
                    if any(keyword in ch_group.lower() for keyword in ['vod', 'movie', 'cinema', 'film', 'series']):
                        continue

                    # --- STRATEGI ANTI-LOCALHOST PERBAIKAN RADIKAL ---
                    clean_cmd = str(cmd).replace('\\', '').strip()
                    stream_url = ""
                    
                    # Coba minta link via API resmi terlebih dahulu
                    if token and clean_cmd:
                        try:
                            link_req_url = f"{api_url}?type=itv&action=create_link&cmd={requests.utils.quote(clean_cmd)}"
                            link_res = requests.get(link_req_url, headers=headers, timeout=6)
                            if link_res.status_code == 200:
                                res_json = link_res.json()
                                js_data = res_json.get('js', {})
                                raw_resolved_url = ""
                                if isinstance(js_data, dict):
                                    raw_resolved_url = js_data.get('cmd', '') or res_json.get('result', '')
                                elif isinstance(js_data, str):
                                    raw_resolved_url = js_data
                                    
                                if raw_resolved_url:
                                    clean_resolved = raw_resolved_url.replace('ffmpeg ', '').replace('ffrt ', '').strip()
                                    link_match = re.search(r'(http[s]?://\S+)', clean_resolved)
                                    if link_match:
                                        stream_url = link_match.group(1).replace('"', '').replace("'", "")
                        except Exception:
                            pass

                    # Ekstrak ID Stream dari perintah (misal dari "ffrt http://localhost/ch/5417_" -> diambil "5417")
                    stream_id = clean_cmd.split('/')[-1].replace('"', '').replace("'", "").replace('_', '').strip()
                    if not stream_id or len(stream_id) > 10 or not stream_id.isalnum():
                        stream_id = ch_id

                    # JIKA HASILNYA MASIH LOCALHOST ATAU KOSONG, PAKSA RE-WRITE STRUKTUR URL PORTAL
                    if not stream_url or "localhost" in stream_url:
                        # METODE UTAMA BYPASS: Struktur URL Pemutar Portal Langsung yang Valid
                        if token:
                            stream_url = f"{base_url}/play/live.php?mac={MAC_ADDRESS}&stream={stream_id}&token={token}"
                        else:
                            stream_url = f"{base_url}/live/{MAC_ADDRESS}/555/{stream_id}.ts"

                    # Ekstraksi URL Gambar Logo
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
                    
                    # Menyusun Baris Playlist M3U Standar Industri
                    m3u_line = f'#EXTINF:-1 tvg-id="{ch_id}" tvg-name="{safe_name}"'
                    if logo_url:
                        m3u_line += f' tvg-logo="{logo_url}"'
                    m3u_line += f' group-title="{safe_group}",{name}\n'
                    
                    # Menyisipkan Header Agen Pengguna dan Kuki Kredensial MAC langsung di bawah info channel
                    m3u_line += f'#EXTVLCOPT:http-user-agent={user_agent}\n'
                    m3u_line += f'#EXTVLCOPT:http-cookie=mac={MAC_ADDRESS}\n'
                    m3u_line += f'{stream_url}\n'
                    
                    m3u_content += m3u_line
                    count += 1
                    
        except Exception as e:
            print(f"-> Gagal mengurai data JSON: {e}")

        print(f"-> Sukses mengekstrak {count} Live TV channel.")
        total_all_channels += count

    except Exception as e:
        print(f"-> Gagal memproses portal karena masalah jaringan: {e}")
        continue

with open('mac_playlist.m3u', 'w', encoding='utf-8') as f:
    f.write(m3u_content)
print(f"\nSelesai! Berhasil mengamankan total {total_all_channels} Live TV channel tanpa localhost.")
