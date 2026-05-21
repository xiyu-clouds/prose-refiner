(function () {
    // ========== 1. 卡片基础数据（完整38条） ==========
    const baseCards = [
      { id: 1, title: '心之所向', desc: '喜欢就是喜欢，不要让外界想法影响了你内心的真实感受。' },
      { id: 2, title: '真诚的代价', desc: '心诚则灵伤深也，若无其事否？诚幽则踽无行也，未雨绸缪否？俭入奢易，奢入俭难，其亦如此。' },
      { id: 3, title: '忠于心，困于心', desc: '忠于心者亦迷于心也。' },
      { id: 4, title: '虚静明心', desc: '安以虚静，然以明心，是谓安然；心若止水，意自澄明，方得始终；虚静以安，明心以然，周流往复，心宽地广。' },
      { id: 5, title: '真实与虚构', desc: '虚构的世界可以反映出现实中最真实的情感。' },
      { id: 6, title: '认识你自己', desc: '了解自己比了解世界更重要。' },
      { id: 7, title: '一往而深', desc: '虽不知此情是否非彼情，但殊途同归，皆是一往而深。' },
      { id: 8, title: '无执于物', desc: '馒头就水也能活，山珍海味亦无妨。' },
      { id: 9, title: '在世而出世', desc: '我在此处，但不止于此处；我似常人，却远非常人。' },
      { id: 10, title: '未诉之语', desc: '阁楼的小窗被风搅得不停吱呀作响，雨珠顺着窗棂缓缓滑落，像是正在哭诉的少女...' },
      { id: 11, title: '心性为上', desc: '不迷信形式，强调心性的纯粹与觉知。' },
      { id: 12, title: '净欲之爱', desc: '天国之恋，只有境界到了，消除了贪嗔痴，仅保留欲望本身的自然的天国儿女方能演绎。' },
      { id: 13, title: '与矛盾共舞', desc: '人是矛盾和不清醒的，既要也要才是常态。用感性去选择，用理性来分析，综合考量，既不忽略真实的情感，亦不忽视客观的事实。' },
      { id: 14, title: '谢了又红', desc: '绿萝襟里藏春，雁叫三声长别，青衣红袖，洗尽尘冬霜雪，桃花谢了又红。' },
      { id: 15, title: '有界的坦诚', desc: '真正的信任不是毫无保留的信任对方，而是彼此理解基础上的选择性开放。' },
      { id: 16, title: '心海无言', desc: '人心如海，暗流之下皆是未诉之言...' },
      { id: 17, title: '痛即真实', desc: '即便世界是假的，但至少这一刻的痛是真的。' },
      { id: 18, title: '演给谁看', desc: '我们都是戏子……演给谁看？' },
      { id: 19, title: '心海无岸', desc: '心海之外，仍有心海。' },
      { id: 20, title: '无心即有心', desc: '整个乌尔姆斯都说安芮是一个无心之人，可老主教却说他是乌尔姆斯唯一有心之人。' },
      { id: 21, title: '微光穿暗', desc: '即便是最深的黑暗，也会有一丝光明穿透。' },
      { id: 22, title: '心即天堂', desc: '我们所追求的天堂，其实就存在于心中。' },
      { id: 23, title: '雨是记忆的回响', desc: '细雨蒙蒙，打湿了古老的石板路，水珠顺着屋檐滴答作响，似是岁月滴落的记忆，每一声都是往昔故事的回响。' },
      { id: 24, title: '他活在你心里吗', desc: '其实，掉落在山洞里的那个郗煜是否死去不重要，真正重要的是：你心中的那个郗煜还活着吗？' },
      { id: 25, title: '杏雨入喉', desc: '温一壶杏花微雨入喉，坐拥青山听笙歌。' },
      { id: 26, title: '墨涸犹待续', desc: '离愁碾作檐下雨，砚池墨涸犹待续。' },
      { id: 27, title: '笺烬桃夭', desc: '今朝有酒今朝醉，桃夭灼灼笺成烬。' },
      { id: 28, title: '与谁说诉', desc: '离愁别恨碎碎扰，又与谁人说诉？' },
      { id: 29, title: '似是而非', desc: '晨露坠叶间，凉意忽沾襟，鸟欢啼，风舞叶；漫步廊间晓月，满地黄花堆积，过小桥，听流水。风走过，雨走过，笑曳如花；小道里，风诉叶语，絮儿叨叨。百八十步，鸟鹊声起，盈步轻轻，心事重重；光洒下，影班驳，似是而非。' },
      { id: 30, title: '囚笼无界', desc: '囚笼内外，谁分得清？' },
      { id: 31, title: '人非神佛', desc: '行为与内心相互映射，推演的可靠性取决于我们对心理和行为的理解深度，以及对客观存在和个体不可控因素的掌握程度。可有些事情并不受个人意志控制，即使暂时超越了人性也难以持久。真能彻底跳脱人性者，已非人类，而是神、仙、妖、魔、佛、道，就是不是人。' },
      { id: 32, title: '剥尽我是谁', desc: '当剥离社会身份与叙事伪装，你的本质还剩什么？' },
      { id: 33, title: '一响惊尘', desc: '陶碗落桌的闷响惊起一旭尘烟...' },
      { id: 34, title: '活着的悖论', desc: '当一个人学会与矛盾共舞，在动态平衡中创造独属自己的生存语法，他便超越了和解与否的二元困境，成为活着的悖论，流动的哲学，未完成却完满的生命诗篇。他的平衡不是终点，而是永动的钟摆——向左摆是人性，向右摆是神性，而他在摆动的轨迹中，写满了凡人不敢直视的真相。这样的存在或许痛苦，却美得惊心动魄。就像深秋最后一片悬在枝头的叶，不坠落不是畏惧寒冬，而是要以摇摇欲坠的姿态，完成对季节最深刻的注解。' },
      { id: 35, title: '不敢看心海', desc: '你总在避免直视自己的心海，就像作者害怕面对笔下角色的质问。' },
      { id: 36, title: '主角与配角', desc: '每个人都是自己故事中的主角，同时也是别人故事里的配角。' },
      { id: 37, title: '碎片成光', desc: '突然间，所有的碎片都拼合在一起，那隐藏在表象之下的真相如同黎明的曙光般清晰可见。' },
      { id: 38, title: '映射体在问', desc: '当映射体开始质疑自身的存在性，本体将听见心海涨潮的声音。' }
    ];

// ========== 2. 图片管理器 ==========
    const CardImageManager = {
        totalImages: 0,
        refreshInterval: 0,
        timerId: null,
        cards: [],

        async loadConfig() {
            const res = await fetch('/api/card-config');
            if (!res.ok) throw new Error('无法获取卡片配置');
            const data = await res.json();
            this.totalImages = data.image_count;
            this.refreshInterval = data.refresh_interval_ms;
        },

        getRandomImageIds(count) {
            const max = this.totalImages;
            const nums = new Set();
            while (nums.size < count) {
                nums.add(Math.floor(Math.random() * max) + 1);
            }
            return Array.from(nums);
        },

        refreshCards() {
            if (this.totalImages > 0) {
                const imageIds = this.getRandomImageIds(baseCards.length);
                this.cards = baseCards.map((card, i) => ({
                    ...card,
                    image: `/static/images/${imageIds[i]}.png`
                }));
            } else {
                this.cards = baseCards.map(card => ({ ...card, image: '' }));
            }
            // 同步到 Alpine Store
            const store = Alpine.store('app');
            if (store) {
                // 用 splice 清空并追加，触发响应式
                store.cards.splice(0, store.cards.length, ...this.cards);
            }
        },

        startAutoRefresh() {
            this.stopAutoRefresh();
            if (this.refreshInterval > 0) {
                this.timerId = setInterval(() => this.refreshCards(), this.refreshInterval);
            }
        },

        stopAutoRefresh() {
            if (this.timerId) {
                clearInterval(this.timerId);
                this.timerId = null;
            }
        },

        async init() {
            try {
                await this.loadConfig();
            } catch (e) {
                console.warn('卡片配置加载失败，使用空图片', e);
                this.totalImages = 0;
                this.refreshInterval = 0;
            }
            this.refreshCards();
            this.startAutoRefresh();
        }
    };

    // 暴露管理器
    window.CardImageManager = CardImageManager;

    // ========== 3. 注册 Alpine Store ==========
    document.addEventListener('alpine:init', () => {
        Alpine.store('app', {
            cards: CardImageManager.cards
        });

        // 启动卡片管理器
        CardImageManager.init();
    });

    window.addEventListener('DOMContentLoaded', () => {
        initSSEForNotifications();
    });
})();