"""Local ASR transcript comparison; not a phonetic pronunciation assessment."""
import re

def tokens(text):
    text=text.lower().replace('’',"'")
    contractions={"i'm":"i am","it's":"it is","that's":"that is","he's":"he is","she's":"she is","don't":"do not","doesn't":"does not","didn't":"did not","can't":"can not","cannot":"can not","won't":"will not","isn't":"is not","aren't":"are not","wasn't":"was not","weren't":"were not","let's":"let us"}
    for old,new in contractions.items(): text=re.sub(r'\b'+re.escape(old)+r'\b',new,text)
    text=re.sub(r"\b(\w+)'re\b",r'\1 are',text)
    text=re.sub(r"\b(\w+)'ve\b",r'\1 have',text)
    text=re.sub(r"\b(\w+)'ll\b",r'\1 will',text)
    return re.findall(r"[a-z]+(?:'[a-z]+)?",text)

def compare(reference,transcript):
    expected,heard=tokens(reference),tokens(transcript)
    if not expected: raise ValueError('原文没有可评分的英文词')
    if len(expected)>2000 or len(heard)>3000: raise ValueError('文本过长，无法评分')
    n,m=len(expected),len(heard)
    dp=[list(range(m+1))]+[[i]+[0]*m for i in range(1,n+1)]
    for i in range(1,n+1):
        for j in range(1,m+1):dp[i][j]=min(dp[i-1][j]+1,dp[i][j-1]+1,dp[i-1][j-1]+(expected[i-1]!=heard[j-1]))
    details=[];i,j=n,m;matched=0
    while i or j:
        if i and j and dp[i][j]==dp[i-1][j-1]+(expected[i-1]!=heard[j-1]):
            if expected[i-1]==heard[j-1]:matched+=1
            else:details.append({'kind':'substitution','expected':expected[i-1],'heard':heard[j-1]})
            i-=1;j-=1
        elif i and dp[i][j]==dp[i-1][j]+1:details.append({'kind':'missing','expected':expected[i-1],'heard':''});i-=1
        else:details.append({'kind':'extra','expected':'','heard':heard[j-1]});j-=1
    return {'score':round(max(0,1-dp[n][m]/n)*100),'matched':matched,'expectedCount':n,'recognizedCount':m,'details':details[::-1],
            'method':'离线识别文本匹配；100 × max(0, 1 − (替换 + 遗漏 + 多读) / 原文词数)'}
