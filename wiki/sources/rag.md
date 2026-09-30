---
title: "检索增强生成（RAG）"
type: source
tags: [rag, retrieval, llm]
date: 2024-01-01
source_file: raw/rag.md
---

## Summary
RAG 将检索与生成结合：先检索相关文档，再由大语言模型基于检索结果作答，从而缓解模型知识过时与幻觉问题。常见组件包括 [[向量数据库]]、Embedding 与 [[重排序]]。

## Key Claims
- RAG 结合检索与生成，先检索相关文档再用 LLM 回答
- RAG 解决大模型知识过时与幻觉问题
- 常见组件：[[向量数据库]]、Embedding、[[重排序]]

## Key Quotes
> "RAG 结合了检索与生成，先检索相关文档再用 LLM 回答。"

## Connections
- [[RAG]] — 本源文档的核心概念
- [[向量数据库]] — RAG 的关键存储组件
- [[检索]] — RAG 流程的前半部分
- [[重排序]] — 提升检索结果质量的后处理步骤

## Contradictions
- 暂无
