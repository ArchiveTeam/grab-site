# This script will check for warc files in specified folder every X specified secounds and upload it to archive.org
# I am not responsible if it damages your system :-)

# You need installed internetarchive package (debian-based distros) and configure it before running this script
# For other distributions and more informations check https://internetarchive.readthedocs.io/en/stable/cli.html

# !!! WARNING !!! THIS SCRIPT IS BUGGY! WARC file will be deleted even if there was issue with uploading !
# YOU'RE WELCOME TO FIX AND/OR UPGRADE THIS SCRIPT!

warcsdir=/example/location  # set your warcs PATH, works if absolute
waittime=30             # wait time between checks, in secounds

while true; do
ls -1 $warcsdir/* > /dev/null 2>&1
if [ "$?" = "0" ]; then
        rm -f $warcsdir/*meta.warc.gz
        rm -f $warcsdir/*.cdx
        FILES=`ls $warcsdir`
        for file in $FILES; do
                echo "Found file $file"
                ia upload $file $warcsdir/$file -m mediatype:web -m subject:archiveteam -v
                echo "Uploaded $file"
                echo "Removing $file"
                rm -f $warcsdir/$file
                FILES=`ls $warcsdir`
        done
else
        echo "No file Found"
        FILES=`ls $warcsdir`
        sleep $waittime
fi
done
