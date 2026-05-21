(function () {
  const ApiClient = {
    async analyze(payload) {
      const res = await axios.post("/api/process", payload);
      return res.data;
    },
    // async test() {
    //   const res = await axios.get("/api/test");
    //   return res.data;
    // },
    initSSEListener() {
      window.connectGlobalSSE();

      window.listenSSE('connection_start', (data) => {
        window.updateSSEStatus('success', '🟢 已连接');
        window.addLog('[INFO] SSE 连接已建立', 'success');
        handleSSEEvent('connection_start', JSON.stringify(data));
      });

      window.listenSSE('task_started', (data) => {
        handleSSEEvent('task_started', JSON.stringify(data));
      });

      window.listenSSE('preprocessing_progress', (data) => {
        handleSSEEvent('preprocessing_progress', JSON.stringify(data));
      });

      window.listenSSE('pipeline_progress', (data) => {
        handleSSEEvent('pipeline_progress', JSON.stringify(data));
      });

      window.listenSSE('metacognition_progress', (data) => {
        handleSSEEvent('metacognition_progress', JSON.stringify(data));
      });

      window.listenSSE('task_completed', (data) => {
        handleSSEEvent('task_completed', JSON.stringify(data));
      });

      window.listenSSE('task_failed', (data) => {
        handleSSEEvent('task_failed', JSON.stringify(data));
      });

      window.listenSSE('connection_close', (data) => {
        window.updateSSEStatus('error', '❌ 已断开');
        window.addLog('[ERROR] SSE 连接已断开', 'error');
        handleSSEEvent('connection_close', JSON.stringify(data));
      });

      window.listenSSE('human_intervention_required', (data) => {
        window.showInterventionModal(data);
      });
    }
  };

  // 页面加载时初始化 SSE 监听
  window.addEventListener('DOMContentLoaded', () => {
    ApiClient.initSSEListener();
  });

  function handleSSEEvent(eventType, data) {
    try {
      const { message, logType, title, status } = window.formatSSEMessage(eventType, data);
      window.addLog(message, logType);
      if (title && window.TaskNotifications) {
        window.TaskNotifications.add(title, status);
      }
    } catch (e) {
      window.addLog(`解析事件数据失败: ${data}`, 'error');
    }
  }

  window.analyze = async function () {
    const text = document.getElementById("inputText").value.trim();
    if (!text) {
      window.showStatus("请输入文本内容", "error");
      return;
    }

    const btn = document.getElementById("analyzeBtn");
    const idleLoader = document.getElementById("idleLoader");
    const activeLoader = document.getElementById("activeLoader");

    // 禁用按钮 & 显示加载状态
    btn.disabled = true;
    idleLoader.style.display = "none";
    activeLoader.style.display = "block";


    try {
        // 确保 SSE 连接已建立
        window.connectGlobalSSE();

        const cardData = window.NovelCards.getData();
        const payload = {
          current_text: text,
          character_profiles: cardData.character_profiles,
          relationship_map: cardData.relationship_map,
          worldview_rules: cardData.worldview_rules,
          style_preference: cardData.style_preference,
        };

        const data = await ApiClient.analyze(payload);

        if (data && data.status === "success") {
          const taskId = data.id || "未知";
          window.showStatus(`✅ 处理完成 (任务ID: ${taskId})`, "success");
        } else {
          const msg = data?.message || "处理失败";
          window.showStatus(msg, "error");
        }
      } catch (err) {
        const msg = err.response?.data?.detail || "分析服务异常，请稍后重试";
        window.showStatus(msg, "error");
        console.error("请求失败:", err);
      } finally {
        btn.disabled = false;
        idleLoader.style.display = "block";
        activeLoader.style.display = "none";
      }
  };

  // document.addEventListener('DOMContentLoaded', () => {
  //   ApiClient.test();
  // });
})();