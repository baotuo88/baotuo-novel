<!-- AIMETA P=世界图谱区_世界观树与关系图可视化|R=树形图_关系图_节点详情|NR=不含编辑功能|E=component:WorldGraphSection|X=ui|A=图谱组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="world-graph-section">
    <div class="section-header">
      <div>
        <h3 class="section-title">世界图谱</h3>
        <p class="section-subtitle">世界观树 + 人物关系图，支持快速定位设定结构与冲突链路</p>
      </div>
      <div class="stats-row">
        <span class="stat-chip">树节点 {{ worldTreeNodes.length }}</span>
        <span class="stat-chip">关系节点 {{ relationNodes.length }}</span>
        <span class="stat-chip">关系边 {{ relationEdges.length }}</span>
      </div>
    </div>

    <div class="tab-row">
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'tree' }"
        @click="activeTab = 'tree'"
      >
        世界观树
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'graph' }"
        @click="activeTab = 'graph'"
      >
        人物关系图
      </button>
    </div>

    <div v-if="!worldTreeNodes.length && !relationNodes.length" class="empty-state">
      暂无可视化数据，先完善世界设定、角色与关系后再查看图谱。
    </div>

    <div v-else-if="activeTab === 'tree'" class="canvas-card">
      <div class="canvas-wrap">
        <svg :width="worldTreeLayout.width" :height="worldTreeLayout.height" class="graph-svg">
          <g v-for="edge in worldTreeEdges" :key="edge.id">
            <line
              :x1="getWorldNodePos(edge.source).x"
              :y1="getWorldNodePos(edge.source).y"
              :x2="getWorldNodePos(edge.target).x"
              :y2="getWorldNodePos(edge.target).y"
              class="edge-line"
            />
          </g>

          <g
            v-for="node in worldTreeNodes"
            :key="node.id"
            class="node-group"
            @click="selectNode(node)"
          >
            <rect
              :x="getWorldNodePos(node.id).x - 62"
              :y="getWorldNodePos(node.id).y - 22"
              width="124"
              height="44"
              rx="12"
              :class="`node-box node-${node.node_type}`"
            />
            <text
              :x="getWorldNodePos(node.id).x"
              :y="getWorldNodePos(node.id).y + 4"
              text-anchor="middle"
              class="node-text"
            >
              {{ shortLabel(node.label, 12) }}
            </text>
          </g>
        </svg>
      </div>
    </div>

    <div v-else class="canvas-card">
      <div class="canvas-wrap">
        <svg :width="relationLayout.width" :height="relationLayout.height" class="graph-svg">
          <defs>
            <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
              <path d="M0,0 L8,4 L0,8 z" class="arrow-head" />
            </marker>
          </defs>

          <g v-for="edge in relationEdges" :key="edge.id">
            <line
              :x1="getRelationNodePos(edge.source).x"
              :y1="getRelationNodePos(edge.source).y"
              :x2="getRelationNodePos(edge.target).x"
              :y2="getRelationNodePos(edge.target).y"
              class="edge-line"
              marker-end="url(#arrow)"
            />
            <text
              :x="(getRelationNodePos(edge.source).x + getRelationNodePos(edge.target).x) / 2"
              :y="(getRelationNodePos(edge.source).y + getRelationNodePos(edge.target).y) / 2 - 6"
              text-anchor="middle"
              class="edge-text"
            >
              {{ edge.label || edge.relation }}
            </text>
          </g>

          <g
            v-for="node in relationNodes"
            :key="node.id"
            class="node-group"
            @click="selectNode(node)"
          >
            <circle
              :cx="getRelationNodePos(node.id).x"
              :cy="getRelationNodePos(node.id).y"
              :r="node.group === 'character' ? 22 : node.group === 'faction' ? 24 : 18"
              :class="`node-circle node-${node.group}`"
            />
            <text
              :x="getRelationNodePos(node.id).x"
              :y="getRelationNodePos(node.id).y + 4"
              text-anchor="middle"
              class="node-text"
            >
              {{ shortLabel(node.label, 6) }}
            </text>
          </g>
        </svg>
      </div>
    </div>

    <div v-if="selectedNode" class="detail-card">
      <div class="detail-title">{{ selectedNode.label }}</div>
      <div class="detail-meta">类型：{{ selectedNode.node_type }} / 分组：{{ selectedNode.group }}</div>
      <pre class="detail-json">{{ JSON.stringify(selectedNode.meta || {}, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { GraphEdge, GraphNode, WorldGraphResponse } from '@/api/novel'

const props = defineProps<{
  data: WorldGraphResponse | null
}>()

const activeTab = ref<'tree' | 'graph'>('tree')
const selectedNode = ref<GraphNode | null>(null)

const worldTreeNodes = computed<GraphNode[]>(() => props.data?.world_tree?.nodes || [])
const worldTreeEdges = computed<GraphEdge[]>(() => props.data?.world_tree?.edges || [])
const relationNodes = computed<GraphNode[]>(() => props.data?.relation_graph?.nodes || [])
const relationEdges = computed<GraphEdge[]>(() => props.data?.relation_graph?.edges || [])

const shortLabel = (value: string, maxLength = 12) => {
  if (!value) return ''
  return value.length > maxLength ? `${value.slice(0, maxLength)}…` : value
}

const selectNode = (node: GraphNode) => {
  selectedNode.value = node
}

const worldTreeLayout = computed(() => {
  const levels = new Map<number, GraphNode[]>()
  worldTreeNodes.value.forEach((node) => {
    const level = node.level ?? 0
    const current = levels.get(level) || []
    current.push(node)
    levels.set(level, current)
  })

  const sortedLevels = Array.from(levels.keys()).sort((a, b) => a - b)
  const pos = new Map<string, { x: number; y: number }>()
  const xGap = 170
  const yGap = 120
  const paddingX = 90
  const paddingY = 50

  let maxInLevel = 1
  sortedLevels.forEach((level) => {
    const nodes = levels.get(level) || []
    nodes.sort((a, b) => a.label.localeCompare(b.label))
    maxInLevel = Math.max(maxInLevel, nodes.length)
    nodes.forEach((node, index) => {
      const x = paddingX + index * xGap
      const y = paddingY + level * yGap
      pos.set(node.id, { x, y })
    })
  })

  return {
    width: Math.max(760, paddingX * 2 + (maxInLevel - 1) * xGap + 120),
    height: Math.max(360, paddingY * 2 + (sortedLevels.length - 1) * yGap + 80),
    pos,
  }
})

const getWorldNodePos = (nodeId: string) => worldTreeLayout.value.pos.get(nodeId) || { x: 0, y: 0 }

const relationLayout = computed(() => {
  const width = 1000
  const height = 620
  const pos = new Map<string, { x: number; y: number }>()

  const chars = relationNodes.value.filter((n) => n.group === 'character')
  const factions = relationNodes.value.filter((n) => n.group === 'faction')
  const others = relationNodes.value.filter((n) => n.group !== 'character' && n.group !== 'faction')

  const placeCircle = (
    nodes: GraphNode[],
    centerX: number,
    centerY: number,
    radius: number
  ) => {
    if (!nodes.length) return
    if (nodes.length === 1) {
      pos.set(nodes[0].id, { x: centerX, y: centerY })
      return
    }
    nodes.forEach((node, index) => {
      const angle = (Math.PI * 2 * index) / nodes.length - Math.PI / 2
      pos.set(node.id, {
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
      })
    })
  }

  placeCircle(chars, width * 0.28, height * 0.44, 180)
  placeCircle(factions, width * 0.72, height * 0.44, 180)
  placeCircle(others, width * 0.5, height * 0.82, 120)

  return { width, height, pos }
})

const getRelationNodePos = (nodeId: string) => relationLayout.value.pos.get(nodeId) || { x: 0, y: 0 }
</script>

<style scoped>
.world-graph-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.section-title {
  margin: 0;
  font-size: 1.06rem;
  font-weight: 700;
  color: #0f172a;
}

.section-subtitle {
  margin: 2px 0 0;
  font-size: 0.86rem;
  color: #64748b;
}

.stats-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.stat-chip {
  display: inline-flex;
  border: 1px solid #dbe3f0;
  background: #f8fbff;
  color: #334155;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
}

.tab-row {
  display: flex;
  gap: 8px;
}

.tab-btn {
  border: 1px solid #dbe3f0;
  background: #fff;
  color: #475569;
  border-radius: 10px;
  padding: 8px 14px;
  font-size: 13px;
  cursor: pointer;
}

.tab-btn.active {
  background: #0f172a;
  color: #fff;
  border-color: #0f172a;
}

.canvas-card {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: linear-gradient(180deg, #f8fbff 0%, #fefefe 100%);
}

.canvas-wrap {
  overflow: auto;
  padding: 10px;
}

.graph-svg {
  display: block;
  min-width: 100%;
}

.edge-line {
  stroke: #cbd5e1;
  stroke-width: 1.4;
}

.edge-text {
  fill: #64748b;
  font-size: 11px;
}

.arrow-head {
  fill: #cbd5e1;
}

.node-group {
  cursor: pointer;
}

.node-box {
  stroke-width: 1.2;
}

.node-world_root {
  fill: #dcfce7;
  stroke: #22c55e;
}

.node-world_key {
  fill: #e0f2fe;
  stroke: #38bdf8;
}

.node-world_item,
.node-world_leaf,
.node-world_value {
  fill: #f8fafc;
  stroke: #94a3b8;
}

.node-circle {
  stroke-width: 1.4;
}

.node-character {
  fill: #eff6ff;
  stroke: #3b82f6;
}

.node-faction {
  fill: #fef3c7;
  stroke: #f59e0b;
}

.node-text {
  fill: #0f172a;
  font-size: 12px;
  font-weight: 600;
  user-select: none;
  pointer-events: none;
}

.detail-card {
  border: 1px solid #e2e8f0;
  background: #ffffff;
  border-radius: 12px;
  padding: 12px;
}

.detail-title {
  font-weight: 700;
  color: #0f172a;
}

.detail-meta {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
}

.detail-json {
  margin: 10px 0 0;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px;
  font-size: 12px;
  line-height: 1.5;
  color: #334155;
  max-height: 240px;
  overflow: auto;
}

.empty-state {
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  color: #64748b;
  text-align: center;
  padding: 40px 20px;
}

@media (max-width: 767px) {
  .tab-btn {
    flex: 1;
  }
}
</style>
