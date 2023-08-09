import os
import os.path
import sys
import json
import zipfile
import shutil
import time
import random
import re
import argparse
import undetected_chromedriver as uc
import appdirs
import requests
import yt_dlp
from colorama import init as colorama_init
from colorama import Fore
from colorama import Style


APP_NAME = "9anime-dl"
APP_DESCRIPTION = "Download anime from 9anime.to"
DATA_DIR = appdirs.user_data_dir(APP_NAME)
os.makedirs(DATA_DIR, exist_ok=True)


def download_file(url, local_filename):
    # https://stackoverflow.com/questions/16694907/download-large-file-in-python-with-requests
    with requests.get(url, stream=True, allow_redirects=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def prepare_ublock():
    """
    Installs/updates uBlock Origin and returns the extension directory.
    """
    GITHUB_API_URL = "https://api.github.com/repos/gorhill/uBlock/releases/latest"
    LAST_VERSION_FILE = os.path.join(DATA_DIR, "last_ublock_version")
    TARGET_UBLOCK_DIR = os.path.join(DATA_DIR, "uBlock")

    response = requests.get(GITHUB_API_URL)
    latest = json.loads(response.text)
    version = latest["tag_name"]

    if not os.path.exists(LAST_VERSION_FILE):
        last_version = None
    else:
        with open(LAST_VERSION_FILE, "r") as f:
            last_version = f.read().strip()

    if version == last_version:
        print("uBlock Origin up-to-date...")
    else:
        if last_version is None:
            print("uBlock Origin not installed... Installing...")
        else:
            print("uBlock Origin out-of-date... Updating...")

        TARGET_ZIP_FILE = os.path.join(DATA_DIR, "uBlock.zip")
        found = False

        if os.path.exists(TARGET_ZIP_FILE):
            os.remove(TARGET_ZIP_FILE)

        for item in latest["assets"]:
            if "chromium" not in item["name"]:
                continue

            dl_url = item["browser_download_url"]
            download_file(dl_url, TARGET_ZIP_FILE)
            found = True

        if not found:
            if last_version is None:
                print("Error: failed to install uBlock Origin")
                sys.exit(1)
            else:
                print("Warning: failed to find newer uBlock Origin asset")
                return

        if os.path.exists(TARGET_UBLOCK_DIR):
            shutil.rmtree(TARGET_UBLOCK_DIR)

        os.makedirs(TARGET_UBLOCK_DIR, exist_ok=True)

        with zipfile.ZipFile(TARGET_ZIP_FILE, "r") as zip_ref:
            zip_ref.extractall(TARGET_UBLOCK_DIR)

        os.remove(TARGET_ZIP_FILE)

        with open(LAST_VERSION_FILE, "w") as f:
            f.write(version)

    unpacked_dirs = []

    for filename in os.listdir(TARGET_UBLOCK_DIR):
        listed_file = os.path.join(TARGET_UBLOCK_DIR, filename)

        if os.path.isdir(listed_file):
            unpacked_dirs.append(listed_file)
        else:
            return TARGET_UBLOCK_DIR

    if len(unpacked_dirs) == 1:
        return unpacked_dirs[0]
    else:
        return TARGET_UBLOCK_DIR


def parse_range(input: str, total_episodes: int) -> list[int]:
    if not input.strip():
        # If not specified, download all by default
        return list(range(1, total_episodes+1))

    episodes_to_download = set()
    parts = input.split(",")

    for part in parts:
        if "-" in part:
            # Handle range
            try:
                begin, end = map(int, part.split("-"))

                if begin < 1:
                    print("Range has to start with at least 1")
                    return False

                if begin > end:
                    print("Range start cannot be bigger than range end")
                    return False

                if end > total_episodes:
                    print("Range end cannot be bigger than available episodes")
                    return False

                episodes_to_download.update(range(begin, end+1))
            except Exception:
                print("Invalid range")
                return False
        else:
            # Handle single episode number
            try:
                ep = int(part)

                if ep < 1:
                    print("Episode number has to be at least 1")
                    return False

                if ep > total_episodes:
                    print("Episode number cannot be bigger than available episodes")
                    return False

                episodes_to_download.add(ep)
            except Exception:
                print("Invalid episode number")
                return False

    return sorted(episodes_to_download)


def ask_which_episodes(total_episodes: int) -> list[int]:
    default_str = "1" if total_episodes == 1 else f"1-{total_episodes}"
    while True:
        print(f"Episodes (Range with '-') {Fore.GREEN}[{default_str}]{Style.RESET_ALL}")
        response = input(">> ").replace(" ", "")
        episodes = parse_range(response, total_episodes)
        print()
        if episodes is not False:
            return episodes


def sleep_random(seconds: int | float):
    diff = random.random() - max(0, min(0.5, seconds - 0.5))
    time.sleep(seconds + diff)


def main(url, sub_version=True, headless=True):
    ublock_dir = prepare_ublock()

    options = uc.ChromeOptions()
    options.add_argument(f"--load-extension={ublock_dir}")

    driver = uc.Chrome(headless=headless, use_subprocess=False, options=options)
    user_agent: str = driver.execute_script("return navigator.userAgent;")

    # Wait until uBlock has loaded
    time.sleep(3)

    driver.get(url)

    # Wait until site has loaded
    time.sleep(1)

    anime_name = driver.find_element(uc.By.CSS_SELECTOR, "h1.title").text.strip()

    print(f"\nDownloading: {anime_name}")

    total_episodes = max(map(lambda x: int(x.get_attribute("data-num")), driver.find_elements(uc.By.CSS_SELECTOR, "a[data-num]")))
    episodes_to_download = ask_which_episodes(total_episodes)

    for episode_number_to_download in episodes_to_download:
        current_episode = int(driver.find_element(uc.By.CSS_SELECTOR, "a.active").get_attribute("data-num"))

        if current_episode != episode_number_to_download:
            # If not selected correct episode, go to correct one
            input_episode_element = driver.find_element(uc.By.CSS_SELECTOR, "div.filter.name > input")
            input_episode_element_value = input_episode_element.get_attribute("value")
            if input_episode_element_value is not None and input_episode_element_value != "":
                input_episode_element.clear()
                sleep_random(1.5)
            input_episode_element.send_keys(episode_number_to_download)
            sleep_random(1.5)
            highlighted_next_episode = driver.find_element(uc.By.CSS_SELECTOR, "a.highlight")
            highlighted_next_episode.click()
            sleep_random(2.5)

        # Find available servers for episode
        servers = driver.find_elements(uc.By.CSS_SELECTOR, f"div.servers > div[data-type='{'sub' if sub_version else 'dub'}'] > ul > li")
        filemoon_server: uc.WebElement | None = None

        for server in servers:
            # Find Filemoon server
            if "Filemoon" in server.text:
                filemoon_server = server
                break

        if filemoon_server is None:
            print(f"Filemoon not available for episode {episode_number_to_download}, skipping...")
            continue

        # If Filemoon server is not selected, select it
        filemoon_class = filemoon_server.get_attribute("class")
        filemoon_is_active = filemoon_class is not None and "active" in filemoon_class

        if not filemoon_is_active:
            filemoon_server.click()
            sleep_random(2.5)

        # Click on player to load Filemoon iframe
        player_div = driver.find_element(uc.By.CSS_SELECTOR, "div#player")
        assert player_div is not None

        while True:
            filemoon_iframe = driver.find_element(uc.By.CSS_SELECTOR, "div#player > iframe")

            if filemoon_iframe is None:
                player_div.click()
                sleep_random(2.5)
            else:
                # If found Filemoon iframe, get download link and download via yt-dlp
                #
                # Example script from Filemoon website:
                # <script data-cfasync="false" type="text/javascript">eval(function(p,a,c,k,e,d){while(c--)if(k[c])p=p.replace(new RegExp('\\b'+c.toString(a)+'\\b','g'),k[c]);return p}('k 9=j("1o");9.7l({7k:[{3b:"13://7j.7i.7h.7g.1u/7f/7e/7d/7c/7b.7a?t=79&s=33&e=78&f=34&77=32&76=74&73=72"}],71:"13://3a-39.1u/70.38",1q:"15%",1p:"15%",6z:"6y",6x:"",6w:"6v",6u:\'6t\',6s:"6r",h:[{3b:"/1m?b=6q&r=6p&6o=13://3a-39.1u/6n.38",6m:"6l"}],6k:{6j:1,1v:\'#6i\',6h:\'#6g\',6f:"6e",6d:30,6c:15,},\'6b\':{"6a":"69"},68:"67",66:"13://2c.2b",65:{},64:12,63:[0.25,0.50,0.75,1,1.25,1.5,2]});k 1s,1t,62;k 61=0,5z=0;k 9=j("1o");k 37=0,5y=0,5x=0,p=0;$.5w({5v:{\'5u-5t\':\'2t-5s\'}});9.l(\'5r\',6(x){g(5>0&&x.y>=5&&1t!=1){1t=1;$(\'w.5q\').5p(\'5o\')}g(x.y>=p+5||x.y<p){p=x.y;1r.5n(\'v\',5m.5l(p),{5k:60*60*24*7})}});9.l(\'14\',6(x){37=x.y});9.l(\'2r\',6(x){36(x)});9.l(\'5j\',6(){$(\'w.35\').5i();1r.2s(\'v\')});6 36(x){$(\'w.35\').5h();g(1s)1g;1s=1;1c=0;g(5g.5f===12){1c=1}$.2z(\'/1m?b=5e&2u=v&5d=34-5c-5b-33-5a&59=1&58=&57=56.55&1c=\'+1c,6(31){$(\'#54\').53(31)});k p=1r.2z(\'v\');g(52(p)>0){21(6(){9.14(p)},51)}$(\'.3-8-4z-4y:4x("4w")\').11(6(e){2y();j().4v(0);j().4u(12)});6 2y(){k $1b=$("<w />").2x({y:"4t",1q:"15%",1p:"15%",4s:0,2v:0,2w:4r,4q:"4p(10%, 10%, 10%, 0.4)","4o-4n":"4m"});$("<4l />").2x({1q:"60%",1p:"60%",2w:4k,"4j-2v":"4i"}).4h({\'4g\':\'/?b=4f&2u=v\',\'4e\':\'0\',\'4d\':\'2t\'}).2q($1b);$1b.11(6(){$(4c).2s();j().2r()});$1b.2q($(\'#1o\'))}j().14(0);}6 4b(){k h=9.1i(2p);2o.2n(h);g(h.r>1){1y(i=0;i<h.r;i++){g(h[i].1h==2p){2o.2n(\'!!=\'+i);9.1w(i)}}}}9.l(\'4a\',6(){j().19("/2l/2k/49.2j","48 10 2i",6(){j().14(j().2h()+10)},"2m");$("w[1d=2m]").2f().2e(\'.3-17-2d\');j().19("/2l/2k/47.2j","46 10 2i",6(){k 1a=j().2h()-10;g(1a<0)1a=0;j().14(1a)},"2g");$("w[1d=2g]").2f().2e(\'.3-17-2d\');});6 1n(){}9.l(\'45\',6(){1n()});9.l(\'44\',6(){1n()});j().19("/29/1m.28","43 42 41",6(){40 u=1l.3z(\'a\');u.2a(\'3y\',\'13://2c.2b/3x/v\');u.2a(\'3w\',\'3v\');1l.1e.3u(u);u.11();1l.1e.3t(u)},"3s");9.l("c",6(18){k h=9.1i();g(h.r<2)1g;$(\'.3-8-3r-3q\').3p(6(){$(\'#3-8-d-c\').16(\'3-8-d-z\');$(\'.3-d-c\').o(\'m-n\',\'q\')});9.19("/29/3o.28","23 22",6(e){$(\'.3-27\').3n(\'3-8-26\');g($(\'.3-27\').3m(\'3-8-26\')){$(\'.3-8-c\').o(\'m-n\',\'12\');$(\'.3-8-d-c \').o(\'m-n\',\'12\');$(\'.3-8-d-c \').3l(\'3-8-d-z\')}3k{$(\'.3-8-c\').o(\'m-n\',\'q\');$(\'.3-8-d-c \').o(\'m-n\',\'q\');$(\'.3-8-d-c \').16(\'3-8-d-z\')}$(\'.3-3j .3-17:3i([m-3h="23 22"])\').l(\'11\',6(){$(\'.3-8-c\').o(\'m-n\',\'q\');$(\'.3-8-d-c \').o(\'m-n\',\'q\');$(\'.3-8-d-c \').16(\'3-8-d-z\')})},"3g");9.l("3f",6(18){1k.3e(\'1j\',18.h[18.3d].1h)});g(1k.20(\'1j\')){21("1z(1k.20(\'1j\'));",3c)}});k 1f;6 1z(1x){k h=9.1i();g(h.r>1){1y(i=0;i<h.r;i++){g(h[i].1h==1x){g(i==1f){1g}1f=i;9.1w(i)}}}}$(\'1e\').l(\'11\',\'.3-17-8\',6(){$(\'.3-8-d-c \').16(\'3-8-d-z\');$(\'.3-1d-1v.3-8-c\').o(\'m-n\',\'q\')})',36,274,'|||jw|||function||settings|videop|||audioTracks|submenu|||if|tracks||jwplayer|var|on|aria|expanded|attr|lastt|false|length|||dl_item|o2lv1o87em9q|div||position|active||click|true|https|seek|100|removeClass|icon|event|addButton|tt|dd|adb|button|body|current_audio|return|name|getAudioTracks|default_audio|localStorage|document|dl|callMeMaybe|vplayer|height|width|ls|vvplay|vvad|com|color|setCurrentAudioTrack|audio_name|for|audio_set|getItem|setTimeout|Track|Audio|||open|controls|svg|images|setAttribute|sx|filemoon|rewind|insertAfter|detach|ff00|getPosition|sec|png|jw8|player|ff11|log|console|track_name|appendTo|play|remove|no|file_code|top|zIndex|css|showCCform|get||data||1691546201|21736020|video_ad|doPlay|prevt|jpg|place|img|file|300|currentTrack|setItem|audioTrackChanged|dualSound|label|not|controlbar|else|addClass|hasClass|toggleClass|dualy|mousedown|buttons|topbar|download11|removeChild|appendChild|_blank|target|download|href|createElement|const|Video|This|Download|playAttemptFailed|beforePlay|Rewind|fr|Forward|ff|ready|set_audio_track|this|scrolling|frameborder|upload_srt|src|prop|50px|margin|1000001|iframe|center|align|text|rgba|background|1000000|left|absolute|pause|setCurrentCaptions|Upload|contains|item|content||500|parseInt|html|fviews|to|aniwave|referer|prem|embed|49b171e413333989c66cf21a35b1aab8|162|254|hash|view|ZorDon|window|hide|show|complete|ttl|round|Math|set|slow|fadeIn|video_ad_fadein|time|cache|Cache|Content|headers|ajaxSetup|v2done|tott|vastdone2||vastdone1|vvbefore|playbackRates|playbackRateControls|cast|aboutlink|FileMoon|abouttext|1080p|2432|qualityLabels|fontOpacity|backgroundOpacity|Tahoma|fontFamily|303030|backgroundColor|FFFFFF|userFontScale|captions|thumbnails|kind|o2lv1o87em9q0000|url|1387|get_slides|start|startparam|auto|preload|html5|primary|duration|uniform|stretching|o2lv1o87em9q_xt|image|2500|sp|3320||asn|srv|43200|zTIZJ0jivD0e8KvrPfp7ilQdFV2ymPi7yFBhXy5YQQQ|m3u8|master|o2lv1o87em9q_x|04347|01|hls2|cdn112|waw05|rcr82|be7713|sources|setup'.split('|')))
                # </script>
                driver.switch_to.frame(filemoon_iframe)

                for script_element in driver.find_elements(uc.By.CSS_SELECTOR, "script[data-cfasync='false']"):
                    script_content = script_element.get_attribute("innerHTML")

                    if not script_content.strip().startswith("eval("):
                        continue

                    unpacked_script = yt_dlp.utils.decode_packed_codes(script_content)
                    m3u8_url = re.search(r'file:"([^"]+)"', unpacked_script)[1]

                    os.makedirs(anime_name, exist_ok=True)

                    safe_anime_name = re.sub("/+", " ", anime_name) # / has a special meaning, so replace it
                    formatted_episode_number = str(episode_number_to_download).zfill(len(str(total_episodes)))
                    output_filename = f"{safe_anime_name}/{safe_anime_name} - {formatted_episode_number}.mp4"

                    headers = {
                        "User-Agent": user_agent,
                        "Referer": "https://filemoon.sx/",
                    }

                    ytdl_options = {
                        "http_headers": headers,
                        "outtmpl": output_filename,
                        "skip_unavailable_fragments": False,
                        "retries": 30,
                        "fragment_retries": 30,
                        "retry_sleep_functions": {
                            "http": lambda n: 1,
                            "fragment": lambda n: 1,
                        }
                    }

                    try:
                        with yt_dlp.YoutubeDL(ytdl_options) as ytdl:
                            ytdl.download(m3u8_url)
                    except Exception:
                        print(f"Failed download for episode {episode_number_to_download}, skipping...")

                    break

                driver.switch_to.default_content()
                break

    # Finally, close the browser
    driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog=APP_NAME, description=APP_DESCRIPTION)
    parser.add_argument('--dub', help='Download dub version', action='store_true')
    parser.add_argument('url', metavar="URL", type=str, help='Anime URL')
    args = parser.parse_args()
    url = args.url
    dub = args.dub
    colorama_init()
    main(url, sub_version=not dub)
