#!/usr/bin/env bash
# 复现 samples/ 下的抓包结果
# 用法:
#   ./reproduce.sh              # 全部重新生成
#   ./reproduce.sh native-chat  # 只生成一个
# 依赖: curl、jq、已启动的 ollama serve、已 pull 的 qwen2.5
set -euo pipefail

HOST="${OLLAMA_HOST:-http://localhost:11434}"
MODEL="${MODEL:-qwen2.5}"
DIR="${OUT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

TOOLS='[{"type":"function","function":{"name":"get_weather","description":"查询指定城市的天气","parameters":{"type":"object","properties":{"city":{"type":"string","description":"城市名称"}},"required":["city"]}}}]'

# 统一出口：$1=路径 $2=JSON body $3=输出文件
post() {
  curl -sSN "$HOST$1" -H 'Content-Type: application/json' -d "$2" -o "$DIR/$3"
  echo "→ $3"
}

# 手工复刻 qwen2.5 模板，供 /api/generate + raw:true 使用。
# raw:true 会跳过 Ollama 的模板和工具注入，所以工具说明必须自己拼进去。
raw_prompt() {
  local user_text="$1"
  cat <<EOF
<|im_start|>system
You are Qwen, created by Alibaba Cloud. You are a helpful assistant.

# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
${TOOLS}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>
<|im_end|>
<|im_start|>user
${user_text}<|im_end|>
<|im_start|>assistant
EOF
}

run() {
  local body
  case "$1" in
    native-chat)
      body=$(jq -n --arg m "$MODEL" '{
        model: $m, stream: false,
        messages: [{role: "user", content: "用一句话解释什么是 token，不超过30字。"}],
        options: {num_predict: 40}
      }')
      post /api/chat "$body" native-chat.json
      ;;
    native-stream)
      body=$(jq -n --arg m "$MODEL" '{
        model: $m, stream: true,
        messages: [{role: "user", content: "用一句话解释什么是 token，不超过30字。"}],
        options: {num_predict: 12}
      }')
      post /api/chat "$body" native-stream.ndjson
      ;;
    native-tool-call)
      body=$(jq -n --arg m "$MODEL" --argjson t "$TOOLS" '{
        model: $m, stream: false, tools: $t,
        messages: [{role: "user", content: "北京今天天气怎么样？"}],
        options: {seed: 42}
      }')
      post /api/chat "$body" native-tool-call.json
      ;;
    native-tool-stream)
      body=$(jq -n --arg m "$MODEL" --argjson t "$TOOLS" '{
        model: $m, stream: true, tools: $t,
        messages: [{role: "user", content: "北京今天天气怎么样？"}],
        options: {seed: 42}
      }')
      post /api/chat "$body" native-tool-stream.ndjson
      ;;
    native-parallel-tool-calls)
      body=$(jq -n --arg m "$MODEL" --argjson t "$TOOLS" '{
        model: $m, stream: false, tools: $t,
        messages: [{role: "user", content: "北京和上海今天天气怎么样？两个城市都要查。"}],
        options: {seed: 42}
      }')
      post /api/chat "$body" native-parallel-tool-calls.json
      ;;
    native-tool-loop)
      body=$(jq -n --arg m "$MODEL" --argjson t "$TOOLS" '{
        model: $m, stream: false, tools: $t,
        messages: [
          {role: "user", content: "北京今天天气怎么样？"},
          {role: "assistant", content: "", tool_calls: [
            {function: {name: "get_weather", arguments: {city: "北京"}}}
          ]},
          {role: "tool", content: "{\"city\":\"北京\",\"weather\":\"晴\",\"temperature\":18}"}
        ]
      }')
      post /api/chat "$body" native-tool-loop.json
      ;;
    native-tool-loop-with-text)
      # 注意: assistant 同时有 content 和 tool_calls 时, Qwen 模板只回放 content
      body=$(jq -n --arg m "$MODEL" --argjson t "$TOOLS" '{
        model: $m, stream: false, tools: $t,
        messages: [
          {role: "user", content: "北京今天天气怎么样？"},
          {role: "assistant",
           content: "我会查询北京的当前天气情况，然后将结果反馈给你。",
           tool_calls: [{function: {name: "get_weather", arguments: {city: "北京"}}}]},
          {role: "tool", content: "{\"city\":\"北京\",\"weather\":\"晴\",\"temperature\":18}"}
        ]
      }')
      post /api/chat "$body" native-tool-loop-with-text.json
      ;;
    raw-model-tool-call)
      body=$(jq -n --arg m "$MODEL" --arg p "$(raw_prompt '北京今天天气怎么样？')" '{
        model: $m, prompt: $p, raw: true, stream: false,
        options: {num_predict: 60, seed: 42}
      }')
      post /api/generate "$body" raw-model-tool-call.json
      ;;
    raw-model-tool-call-with-text)
      # 让模型先说话再调用工具；采样有随机性，跑出来不一定和样本逐字一致
      body=$(jq -n --arg m "$MODEL" --arg p "$(raw_prompt '北京今天天气怎么样？请先说明你要做什么，再调用工具。')" '{
        model: $m, prompt: $p, raw: true, stream: false,
        options: {num_predict: 60}
      }')
      post /api/generate "$body" raw-model-tool-call-with-text.json
      ;;
    raw-model-parallel-tool-calls)
      body=$(jq -n --arg m "$MODEL" --arg p "$(raw_prompt '北京和上海今天天气怎么样？两个城市都要查。')" '{
        model: $m, prompt: $p, raw: true, stream: false,
        options: {num_predict: 120, seed: 42}
      }')
      post /api/generate "$body" raw-model-parallel-tool-calls.json
      ;;
    all)
      for name in native-chat native-stream \
                  native-tool-call native-tool-stream native-parallel-tool-calls \
                  native-tool-loop native-tool-loop-with-text \
                  raw-model-tool-call raw-model-tool-call-with-text raw-model-parallel-tool-calls; do
        run "$name"
      done
      ;;
    *)
      echo "unknown sample: $1" >&2
      echo "可选: native-chat native-stream native-tool-call native-tool-stream" >&2
      echo "      native-parallel-tool-calls native-tool-loop native-tool-loop-with-text" >&2
      echo "      raw-model-tool-call raw-model-tool-call-with-text raw-model-parallel-tool-calls" >&2
      exit 1
      ;;
  esac
}

run "${1:-all}"
