---
title: "env_config.ini"
type: entity
tags: [config-file, deployment]
sources: [升级前配置比对与批量升级流程]
last_updated: 2025-01-01
---

# env_config.ini

系统部署过程中用于定义组件配置的配置文件。

## 关键作用
- 包含模块推荐自动绑定
- 在组件发生变动时，批次二"构建临时运行目录"会报此文件中组件配置与系统存在差异
- 报错时需重新绑定组件并进行网络 ssh 配置

## Connections
- [[组件配置]] — env_config.ini 是组件配置的存储载体
- [[批量升级]] — 组件变动会影响批量升级批次二
- [[应用升级]] — 修复后需重新执行构建临时发布目录
