from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import DocArrayInMemorySearch
from langchain_community.document_loaders import PyPDFLoader
from langchain.chains import ConversationalRetrievalChain
import panel as pn
import param

pn.extension(design='material')  # 使用 Material 设计主题

# --- 配置 ---
OLLAMA_LLM   = "gemma3:4b"
OLLAMA_EMBED = "nomic-embed-text"  
BASE_URL     = None                 

# --- 数据库加载函数 ---
def load_db(file, chain_type, k):
    loader = PyPDFLoader(file)
    documents = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    docs = text_splitter.split_documents(documents)

    embeddings = OllamaEmbeddings(model=OLLAMA_EMBED, base_url=BASE_URL)
    db = DocArrayInMemorySearch.from_documents(docs, embeddings)

    retriever = db.as_retriever(search_type="similarity", search_kwargs={"k": k})

    llm = ChatOllama(model=OLLAMA_LLM, temperature=0, base_url=BASE_URL)

    qa = ConversationalRetrievalChain.from_llm(
        llm=llm,
        chain_type=chain_type,
        retriever=retriever,
        return_source_documents=True,
        return_generated_question=True,
    )
    return qa

# --- 核心类 ---
class cbfs(param.Parameterized):
    chat_history = param.List([])
    answer = param.String("")
    db_query  = param.String("")
    db_response = param.List([])
    loading = param.Boolean(False)  # 新增：加载状态
    
    def __init__(self,  **params):
        super(cbfs, self).__init__( **params)
        self.panels = []
        self.loaded_file = "C:\\Users\\fshyit02\\OneDrive - ANDRITZ AG\\Desktop\\self-resource\\MachineLearningTraining-V1.0 (2).pdf"
        self.qa = load_db(self.loaded_file,"stuff", 4)
    
    def call_load_db(self, count):
        if count == 0 or file_input.value is None:
            return pn.pane.Markdown(f'<div style="color: #4CAF50;">**Loaded File:** {self.loaded_file}</div>')
        else:
            self.loading = True  # 开始加载
            file_input.save("temp.pdf")
            self.loaded_file = file_input.filename
            self.qa = load_db("temp.pdf", "stuff", 4)
            self.loading = False  # 加载完成
            self.clr_history()
            return pn.pane.Markdown(f'<div style="color: #4CAF50;">**Loaded File:** {self.loaded_file}</div>')

    def convchain(self, query: str):
        if not query:
            return pn.Column()

        self.loading = True  # 开始加载
        result = self.qa({"question": query, "chat_history": self.chat_history})
        self.chat_history.append((query, result["answer"]))
        self.db_query = result["generated_question"]
        self.db_response = result["source_documents"]
        self.answer = result['answer'] 
        self.loading = False  # 加载完成

        # 构建聊天气泡
        user_bubble = pn.pane.Markdown(
            f"<div style='background-color: #E3F2FD; padding: 10px; border-radius: 15px; margin-bottom: 10px; max-width: 70%; margin-left: auto;'>{query}</div>",
            width=600
        )
        bot_bubble = pn.pane.Markdown(
            f"<div style='background-color: #F5F5F5; padding: 10px; border-radius: 15px; margin-bottom: 10px; max-width: 70%;'>{self.answer}</div>",
            width=600
        )

        self.panels.extend([user_bubble, bot_bubble])
        inp.value = ''
        return pn.Column(*self.panels, scroll=True, height=400)

    @param.depends('db_query', 'loading')
    def get_lquest(self):
        if self.loading:
            return pn.Column(
                pn.pane.Markdown('<div style="background-color: #E8F5E8; padding: 5px;">**DB Query:**</div>'),
                pn.pane.Markdown('<div style="color: #90A4AE;">Loading...</div>')
            )
        if not self.db_query:
            return pn.Column(
                pn.pane.Markdown('<div style="background-color: #E8F5E8; padding: 5px;">**DB Query:**</div>'),
                pn.pane.Markdown('<div style="color: #90A4AE;">No DB accesses yet.</div>')
            )
        return pn.Column(
            pn.pane.Markdown('<div style="background-color: #E8F5E8; padding: 5px;">**DB Query:**</div>'),
            pn.pane.Markdown(f'<div style="background-color: #F1F8E9; padding: 8px; border-radius: 5px;">> {self.db_query}</div>')
        )
    
    @param.depends('db_response', 'loading')
    def get_sources(self):
        if self.loading:
            return pn.Column(
                pn.pane.Markdown('<div style="background-color: #E8F5E8; padding: 5px;">**Sources:**</div>'),
                pn.pane.Markdown('<div style="color: #90A4AE;">Loading sources...</div>')
            )
        if not self.db_response:
            return pn.Column(
                pn.pane.Markdown('<div style="background-color: #E8F5E8; padding: 5px;">**Sources:**</div>'),
                pn.pane.Markdown('<div style="color: #90A4AE;">No sources found.</div>')
            )
        sources = []
        for i, doc in enumerate(self.db_response, 1):
            sources.append(pn.pane.Markdown(
                f'<div style="background-color: #FFF8E1; padding: 8px; border-radius: 5px; margin: 5px 0;">**Source {i}:**\n{doc.page_content[:300]}...</div>'
            ))
        return pn.Column(
            pn.pane.Markdown('<div style="background-color: #E8F5E8; padding: 5px;">**Sources:**</div>'),
            *sources,
            scroll=True,
            height=300
        )

    @param.depends('chat_history', 'loading')
    def get_chats(self):
        if self.loading:
            return pn.pane.Markdown('<div style="color: #90A4AE;">Loading history...</div>')
        if not self.chat_history:
            return pn.pane.Markdown('<div style="color: #90A4AE;">No chat history yet.</div>')
        history = []
        for user_msg, bot_msg in self.chat_history:
            history.append(pn.pane.Markdown(f'<div style="margin: 5px 0;">**You:** {user_msg}</div>'))
            history.append(pn.pane.Markdown(f'<div style="margin: 5px 0; color: #0277BD;">**Bot:** {bot_msg}</div>'))
        return pn.Column(*history, scroll=True, height=400)

    def clr_history(self, count=0):
        self.chat_history = []
        self.panels = []
        return

# --- 初始化组件 ---
cb = cbfs()

file_input = pn.widgets.FileInput(accept='.pdf', width=200)
button_load = pn.widgets.Button(name="Load PDF", button_type='primary', width=120)
button_clearhistory = pn.widgets.Button(name="Clear History", button_type='warning', width=120)
button_clearhistory.on_click(cb.clr_history)
inp = pn.widgets.TextInput(placeholder='Ask a question about the PDF...', width=400)

bound_button_load = pn.bind(cb.call_load_db, button_load.param.clicks)
conversation = pn.bind(cb.convchain, inp.param.value)

# --- 定义卡片样式 ---
card_style = {
    'padding': '15px',
    'border-radius': '10px',
    'box-shadow': '0 2px 5px rgba(0,0,0,0.1)',
    'margin-bottom': '15px'
}

# --- 构建标签页 ---
tab1 = pn.Column(
    pn.Card(
        pn.Row(inp, button_clearhistory),
        title="Conversation",
        styles=card_style
    ),
    pn.layout.Divider(),
    pn.panel(conversation, loading_indicator=True, height=400),
    styles={'padding': '10px'}
)

tab2 = pn.Column(
    pn.Card(
        cb.get_lquest,
        title="Database Query",
        styles=card_style
    ),
    pn.layout.Divider(),
    pn.Card(
        cb.get_sources,
        title="Source Documents",
        styles=card_style
    ),
    styles={'padding': '10px'}
)

tab3 = pn.Column(
    pn.Card(
        cb.get_chats,
        title="Chat History",
        styles=card_style
    ),
    styles={'padding': '10px'}
)

tab4 = pn.Column(
    pn.Card(
        pn.Row(file_input, button_load, bound_button_load),
        title="Load PDF",
        styles=card_style
    ),
    pn.layout.Divider(),
    pn.pane.Markdown('<div style="background-color: #E8F5E8; padding: 5px;">**DB Query:**</div>')
)

# --- 构建仪表盘 ---
dashboard = pn.Column(
    pn.pane.Markdown('<div style="text-align: center; font-size: 24px; margin: 10px 0;"># 📄 PDF Chat Assistant</div>'),
    pn.Tabs(
        ("Chat", tab1),
        ("Database", tab2),
        ("History", tab3),
        ("Settings", tab4),
        dynamic=True  # 动态加载标签页内容
    ),
    styles={'max-width': '1000px', 'margin': '0 auto', 'padding': '20px'}
)

# --- 显示应用 ---
dashboard.show()