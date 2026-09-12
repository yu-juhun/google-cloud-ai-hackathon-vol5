# google-cloud-ai-hackathon-vol5

[Google Cloud Japan AI Hackathon vol.5](https://zenn.dev/hackathons/google-cloud-japan-ai-hackathon-vol5) 参加用リポジトリです。

## 作業前に必読

人間・AIエージェントを問わず、このリポジトリで作業を始める前に必ず
[`docs/wiki/index.md`](docs/wiki/index.md) を読んでください。プロジェクトの方針・
コンテスト要件・チーム体制・協業ルールが `docs/wiki/concepts/steering.md` にまとまっています。

## セットアップ

ADK(Agent Development Kit)エージェントの開発には `google/agents-cli` を使う。
各自のマシンで一度だけ実行する(詳細・理由は [docs/wiki/concepts/agents-cli-adoption.md](docs/wiki/concepts/agents-cli-adoption.md)):

```bash
uvx google-agents-cli setup
```

前提: [uv](https://docs.astral.sh/uv/) がインストールされていること。
