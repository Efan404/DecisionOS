# React / Next.js 降级记录

## 降级原因

React 19.2.3 + Next.js 16.1.6 组合存在严重的兼容性问题：

- **错误**: `Rendered more hooks than during the previous render`
- **位置**: Next.js App Router 内部 (`app-router.tsx`)
- **影响**: 应用完全无法渲染，白屏报错

这是 React 19 与 Next.js App Router 的已知兼容性问题。

## 降级详情

### 降级前版本

| 包                     | 版本     |
| ---------------------- | -------- |
| next                   | 16.1.6   |
| react                  | 19.2.3   |
| react-dom              | 19.2.3   |
| eslint-config-next     | 16.1.6   |
| @types/react           | ^19      |
| @types/react-dom       | ^19      |
| framer-motion          | ^12.34.2 |
| @testing-library/react | ^16.3.2  |

### 降级后版本

| 包                     | 版本         |
| ---------------------- | ------------ |
| next                   | **14.2.35**  |
| react                  | **18.3.1**   |
| react-dom              | **18.3.1**   |
| eslint-config-next     | **14.2.35**  |
| @types/react           | **^18.3.23** |
| @types/react-dom       | **^18.3.5**  |
| framer-motion          | **^11.18.2** |
| @testing-library/react | **^14.3.1**  |

## 配置文件变更

### next.config.ts → next.config.mjs

Next.js 14 不支持 `.ts` 配置文件，需改为 `.mjs`：

```javascript
/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
}

export default config
```

## 降级步骤

```bash
# 1. 备份 package.json
cp package.json package.json.backup.$(date +%Y%m%d_%H%M%S)

# 2. 降级核心依赖
pnpm install next@14.2.35 react@18.3.1 react-dom@18.3.1 \
  eslint-config-next@14.2.35 \
  @types/react@18.3.23 @types/react-dom@18.3.5 \
  --save

# 3. 降级相关库
pnpm install framer-motion@11.18.2 \
  @testing-library/react@14.3.1 \
  --save

# 4. 清理缓存
rm -rf frontend/.next node_modules/.cache

# 5. 重新启动
export NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
pnpm dev:web
```

## 注意事项

1. **环境变量**: Next.js 14 需要明确设置 `NEXT_PUBLIC_API_BASE_URL`
2. **缓存清理**: 降级后必须清理 `.next` 缓存，否则会出现奇怪的错误
3. **Node.js 版本**: 确保使用 Node.js 18+ (测试使用 20.19.5)

## 验证

降级后应用应能正常：

- ✅ 渲染页面
- ✅ 登录功能
- ✅ Idea Canvas DAG 交互
- ✅ AI Expand 功能

## 未来升级

等待以下稳定版本发布后再考虑升级：

- Next.js 15+ (稳定版)
- React 19+ (稳定版，与 Next.js 兼容)

## 参考

- [Next.js 14 文档](https://nextjs.org/docs/14)
- [React 18 文档](https://react.dev/blog/2022/03/29/react-v18)
