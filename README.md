# 9anime-dl

## Setup
Install Python 3. I tested this program with Python 3.11
and I’m not sure how well older Python versions work, for your information.
(By the way, I also only tested this program on Linux,
so I don’t know if it will work on other platforms as well.)

Download program files:
```
$ git clone https://github.com/Funami580/9anime-dl.git
$ cd 9anime-dl
```

Install Chromium, if it isn’t already installed.
Then install the dependencies (listed in pyproject.toml).

## Download
```
$ python main.py 'https://aniwave.to/watch/yuruyuri.p6q/ep-1'
Downloading: YuruYuri
Episodes (Range with '-') [1-12]
>> 1
...
```

With dub:
```
$ python main.py --dub 'https://aniwave.to/watch/yuruyuri.p6q/ep-1'
```
