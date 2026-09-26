Source tapes/common.tape
Set Height 800
Output out/rename.gif
Output out/rename.mp4
Hide
Type "cd scratch/rename && export PS1='$ ' && clear"
Enter
Sleep 500ms
Show
Type "tree --noreport models"
Enter
Sleep 1500ms
Type "mv models/marts/revenue.sql models/finance/daily_revenue.sql"
Sleep 300ms
Enter
Sleep 800ms
Type "sqb plan"
Sleep 300ms
Enter
Wait@60s /\$\s*$/
Sleep 1s
Screenshot out/rename.png
Sleep 10s
