# Common Qwen LiveTranslate targets. Input speech language is auto-detected.
LANGUAGES=[('en','英语',True),('zh','中文',True),('ja','日语',True),('ko','韩语',True),
 ('fr','法语',True),('de','德语',True),('es','西班牙语',True),('pt','葡萄牙语',True),
 ('ru','俄语',True),('ar','阿拉伯语',True),('it','意大利语（文字）',False),
 ('hi','印地语（文字）',False),('id','印度尼西亚语（文字）',False),('vi','越南语（文字）',False),
 ('th','泰语（文字）',False),('tr','土耳其语（文字）',False),('nl','荷兰语（文字）',False),
 ('pl','波兰语（文字）',False),('sv','瑞典语（文字）',False),('uk','乌克兰语（文字）',False)]
def name(code):return next((n for c,n,a in LANGUAGES if c==code),code)
def code(name):return next((c for c,n,a in LANGUAGES if n==name),'en')
def audio(code):return next((a for c,n,a in LANGUAGES if c==code),False)
