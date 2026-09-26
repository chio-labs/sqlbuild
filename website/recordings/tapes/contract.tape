Source tapes/common.tape
Set FontSize 16
Set Width 1600
Set Height 820
Output out/contract.gif
Output out/contract.mp4
Hide
Type "cd scratch/contract && export PS1='$ ' && clear"
Enter
Sleep 500ms
Show
Type "sqb compile --select daily_revenue"
Sleep 300ms
Enter
Wait@60s /\$\s*$/
Sleep 1s
Screenshot out/contract.png
Sleep 15s
