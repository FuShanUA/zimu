@echo off
pushd D:\cc\Library\Tools\autosub
echo Launching AutoSub Batch V4 (DevCon_4)...
powershell -NoExit -Command "python D:\cc\Library\Tools\autosub\autosub_batch_v4.py --output D:\cc\Projects\DevCon_4 --urls https://www.youtube.com/playlist?list=PLqTLGbLI0CvkZmevZavWNOmEo2WNgKMB- --exclude 1,2,4,7,13 --gdsync 1F0YB1IWfAu-Xacj4wgOSw3Jf5EW3Avx3 --cookies D:\Downloads\cookies.txt"
popd
