<!-- AIMETA P=世界图谱区_世界观树与关系图可视化|R=树形图_关系图_节点详情_图谱编辑|NR=不含拖拽布局|E=component:WorldGraphSection|X=ui|A=图谱组件|D=vue|S=dom,net|RD=./README.ai -->
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

    <div v-if="editable && projectId" class="editor-card">
      <div class="editor-head">
        <h4>图谱编辑器</h4>
        <button class="save-btn" :disabled="loadingEditorData" @click="reloadEditorData">
          刷新
        </button>
      </div>
      <p v-if="editorNotice" class="editor-notice">{{ editorNotice }}</p>

      <div class="editor-block">
        <div class="editor-block-title">人物关系</div>
        <div v-for="(item, index) in characterRelationships" :key="`char-rel-${index}`" class="row-grid row-char">
          <input v-model="item.character_from" placeholder="角色A" />
          <input v-model="item.character_to" placeholder="角色B" />
          <input v-model="item.relationship_type" placeholder="关系类型" />
          <input v-model="item.description" placeholder="关系描述（可选）" />
          <button class="danger-btn" @click="removeCharacterRelationship(index)">删除</button>
        </div>
        <div class="editor-actions">
          <button class="add-btn" @click="addCharacterRelationship">新增关系</button>
          <button class="save-btn" :disabled="savingCharacterRelationships" @click="saveCharacterRelationships">
            {{ savingCharacterRelationships ? '保存中...' : '保存人物关系' }}
          </button>
        </div>
      </div>

      <div class="editor-block">
        <div class="editor-block-title">势力清单</div>
        <div v-for="(item, index) in factions" :key="`faction-${index}`" class="row-grid row-faction">
          <input v-model="item.name" placeholder="势力名称" />
          <input v-model="item.faction_type" placeholder="类型（门派/组织）" />
          <input v-model="item.leader" placeholder="领袖（可选）" />
          <button class="danger-btn" @click="removeFaction(index)">删除</button>
        </div>
        <div class="editor-actions">
          <button class="add-btn" @click="addFaction">新增势力</button>
          <button class="save-btn" :disabled="savingFactions" @click="saveFactions">
            {{ savingFactions ? '保存中...' : '保存势力' }}
          </button>
        </div>
      </div>

      <div class="editor-block">
        <div class="editor-block-title">势力关系</div>
        <div v-for="(item, index) in factionRelationships" :key="`faction-rel-${index}`" class="row-grid row-faction-rel">
          <select v-model.number="item.faction_from_id">
            <option :value="0" disabled>起点势力</option>
            <option v-for="f in factionSelectOptions" :key="`from-${f.id}`" :value="f.id">{{ f.name }}</option>
          </select>
          <select v-model.number="item.faction_to_id">
            <option :value="0" disabled>终点势力</option>
            <option v-for="f in factionSelectOptions" :key="`to-${f.id}`" :value="f.id">{{ f.name }}</option>
          </select>
          <input v-model="item.relationship_type" placeholder="关系类型（盟友/敌对）" />
          <input
            type="number"
            min="1"
            max="10"
            v-model.number="item.strength"
            placeholder="强度 1-10"
          />
          <button class="danger-btn" @click="removeFactionRelationship(index)">删除</button>
        </div>
        <div class="editor-actions">
          <button class="add-btn" @click="addFactionRelationship">新增势力关系</button>
          <button class="save-btn" :disabled="savingFactionRelationships" @click="saveFactionRelationships">
            {{ savingFactionRelationships ? '保存中...' : '保存势力关系' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  NovelAPI,
  type FactionItem,
  type FactionRelationshipItem,
  type GraphEdge,
  type GraphNode,
  type WorldGraphResponse
} from '@/api/novel'

interface CharacterRelationshipItem {
  character_from: string
  character_to: string
  relationship_type: string
  description: string
}

const props = defineProps<{
  data: WorldGraphResponse | null
  editable?: boolean
  projectId?: string
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
}>()

const activeTab = ref<'tree' | 'graph'>('tree')
const selectedNode = ref<GraphNode | null>(null)

const editorNotice = ref('')
const loadingEditorData = ref(false)
const savingCharacterRelationships = ref(false)
const savingFactions = ref(false)
const savingFactionRelationships = ref(false)

const characterRelationships = ref<CharacterRelationshipItem[]>([])
const factions = ref<Array<Partial<FactionItem>>>([])
const factionRelationships = ref<FactionRelationshipItem[]>([])

const worldTreeNodes = computed<GraphNode[]>(() => props.data?.world_tree?.nodes || [])
const worldTreeEdges = computed<GraphEdge[]>(() => props.data?.world_tree?.edges || [])
const relationNodes = computed<GraphNode[]>(() => props.data?.relation_graph?.nodes || [])
const relationEdges = computed<GraphEdge[]>(() => props.data?.relation_graph?.edges || [])
const factionSelectOptions = computed(() =>
  factions.value
    .filter((item) => item.id && item.name)
    .map((item) => ({ id: Number(item.id), name: String(item.name) }))
)

const shortLabel = (value: string, maxLength = 12) => {
  if (!value) return ''
  return value.length > maxLength ? `${value.slice(0, maxLength)}…` : value
}

const selectNode = (node: GraphNode) => {
  selectedNode.value = node
}

const toCharacterRelationshipsFromGraph = () => {
  const nodeMap = new Map(relationNodes.value.map((node) => [node.id, node.label]))
  const items: CharacterRelationshipItem[] = relationEdges.value
    .filter((edge) => edge.relation === 'character_relationship')
    .map((edge) => {
      const relationText = String(edge.label || edge.relation || '关系')
      return {
        character_from: String(nodeMap.get(edge.source) || ''),
        character_to: String(nodeMap.get(edge.target) || ''),
        relationship_type: relationText,
        description: relationText,
      }
    })
    .filter((item) => item.character_from && item.character_to)
  characterRelationships.value = items.length ? items : [{
    character_from: '',
    character_to: '',
    relationship_type: '',
    description: '',
  }]
}

const reloadEditorData = async () => {
  if (!props.editable || !props.projectId) return
  loadingEditorData.value = true
  editorNotice.value = ''
  try {
    toCharacterRelationshipsFromGraph()
    const [factionResp, relResp] = await Promise.all([
      NovelAPI.getFactions(props.projectId),
      NovelAPI.getFactionRelationships(props.projectId)
    ])
    factions.value = (factionResp.factions || []).map((item) => ({
      id: item.id,
      name: item.name,
      faction_type: item.faction_type || '',
      leader: item.leader || '',
      description: item.description || '',
      power_level: item.power_level || '',
      current_status: item.current_status || '',
    }))
    factionRelationships.value = (relResp.relationships || []).map((item) => ({
      id: item.id,
      faction_from_id: Number(item.faction_from_id),
      faction_to_id: Number(item.faction_to_id),
      relationship_type: item.relationship_type || '',
      strength: item.strength ?? 5,
      description: item.description || '',
      reason: item.reason || '',
    }))
  } catch (error) {
    editorNotice.value = `编辑器数据加载失败：${error instanceof Error ? error.message : '未知错误'}`
  } finally {
    loadingEditorData.value = false
  }
}

const addCharacterRelationship = () => {
  characterRelationships.value.push({
    character_from: '',
    character_to: '',
    relationship_type: '',
    description: '',
  })
}

const removeCharacterRelationship = (index: number) => {
  characterRelationships.value.splice(index, 1)
}

const saveCharacterRelationships = async () => {
  if (!props.projectId) return
  const payload = characterRelationships.value
    .map((item) => ({
      character_from: item.character_from.trim(),
      character_to: item.character_to.trim(),
      relationship_type: item.relationship_type.trim() || item.description.trim() || '关系',
      description: item.description.trim() || item.relationship_type.trim() || '关系',
    }))
    .filter((item) => item.character_from && item.character_to)

  savingCharacterRelationships.value = true
  editorNotice.value = ''
  try {
    await NovelAPI.updateBlueprint(props.projectId, { relationships: payload })
    editorNotice.value = '人物关系已保存'
    emit('refresh')
  } catch (error) {
    editorNotice.value = `人物关系保存失败：${error instanceof Error ? error.message : '未知错误'}`
  } finally {
    savingCharacterRelationships.value = false
  }
}

const addFaction = () => {
  factions.value.push({
    name: '',
    faction_type: '',
    leader: '',
    description: '',
    power_level: '',
    current_status: '',
  })
}

const removeFaction = (index: number) => {
  factions.value.splice(index, 1)
}

const saveFactions = async () => {
  if (!props.projectId) return
  const rawPayload = factions.value
    .map((item) => ({
      id: item.id,
      name: String(item.name || '').trim(),
      faction_type: String(item.faction_type || '').trim() || null,
      leader: String(item.leader || '').trim() || null,
      description: String(item.description || '').trim() || null,
      power_level: String(item.power_level || '').trim() || null,
      current_status: String(item.current_status || '').trim() || null,
    }))
    .filter((item) => item.name)

  const uniqueByName = new Map<string, (typeof rawPayload)[number]>()
  for (const item of rawPayload) {
    const key = item.name.toLowerCase()
    const existing = uniqueByName.get(key)
    if (!existing) {
      uniqueByName.set(key, item)
      continue
    }
    // 同名时优先保留已有 ID 的记录，避免创建重复势力
    if (!existing.id && item.id) {
      uniqueByName.set(key, item)
    }
  }
  const payload = Array.from(uniqueByName.values())

  savingFactions.value = true
  editorNotice.value = ''
  try {
    const response = await NovelAPI.saveFactions(props.projectId, payload)
    factions.value = response.factions || []
    editorNotice.value = '势力已保存'
    emit('refresh')
  } catch (error) {
    editorNotice.value = `势力保存失败：${error instanceof Error ? error.message : '未知错误'}`
  } finally {
    savingFactions.value = false
  }
}

const addFactionRelationship = () => {
  factionRelationships.value.push({
    faction_from_id: 0,
    faction_to_id: 0,
    relationship_type: '',
    strength: 5,
    description: '',
    reason: '',
  })
}

const removeFactionRelationship = (index: number) => {
  factionRelationships.value.splice(index, 1)
}

const saveFactionRelationships = async () => {
  if (!props.projectId) return
  const rawPayload = factionRelationships.value
    .map((item) => ({
      faction_from_id: Number(item.faction_from_id),
      faction_to_id: Number(item.faction_to_id),
      relationship_type: String(item.relationship_type || '').trim() || 'neutral',
      strength: Math.max(1, Math.min(10, Number(item.strength || 5))),
      description: String(item.description || '').trim() || null,
      reason: String(item.reason || '').trim() || null,
    }))
    .filter((item) => item.faction_from_id > 0 && item.faction_to_id > 0)

  const seenPairs = new Set<string>()
  const payload = rawPayload.filter((item) => {
    if (item.faction_from_id === item.faction_to_id) {
      return false
    }
    const pairKey = `${item.faction_from_id}->${item.faction_to_id}`
    if (seenPairs.has(pairKey)) {
      return false
    }
    seenPairs.add(pairKey)
    return true
  })

  savingFactionRelationships.value = true
  editorNotice.value = ''
  try {
    await NovelAPI.saveFactionRelationships(props.projectId, payload)
    editorNotice.value = '势力关系已保存'
    emit('refresh')
  } catch (error) {
    editorNotice.value = `势力关系保存失败：${error instanceof Error ? error.message : '未知错误'}`
  } finally {
    savingFactionRelationships.value = false
  }
}

watch(
  () => props.data,
  () => {
    toCharacterRelationshipsFromGraph()
  },
  { immediate: true }
)

watch(
  () => [props.editable, props.projectId],
  () => {
    void reloadEditorData()
  },
  { immediate: true }
)

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
  const factionsInGraph = relationNodes.value.filter((n) => n.group === 'faction')
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
  placeCircle(factionsInGraph, width * 0.72, height * 0.44, 180)
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

.node-world_root,
.node-world_key {
  fill: #dbeafe;
  stroke: #3b82f6;
}

.node-world_item,
.node-world_leaf,
.node-world_value {
  fill: #ecfccb;
  stroke: #65a30d;
}

.node-circle {
  stroke-width: 1.4;
}

.node-character {
  fill: #e0f2fe;
  stroke: #0284c7;
}

.node-faction {
  fill: #fef3c7;
  stroke: #d97706;
}

.node-text {
  font-size: 12px;
  font-weight: 600;
  fill: #0f172a;
  pointer-events: none;
}

.detail-card {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 12px;
  background: #ffffff;
}

.detail-title {
  font-weight: 700;
  color: #0f172a;
}

.detail-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}

.detail-json {
  margin: 10px 0 0;
  font-size: 12px;
  line-height: 1.4;
  padding: 10px;
  border-radius: 8px;
  background: #f8fafc;
  color: #334155;
  overflow: auto;
}

.empty-state {
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  padding: 24px;
  text-align: center;
  color: #64748b;
  font-size: 13px;
}

.editor-card {
  border: 1px solid #dbe3f0;
  background: #fcfdff;
  border-radius: 14px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.editor-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.editor-head h4 {
  margin: 0;
  font-size: 15px;
  color: #0f172a;
}

.editor-notice {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: #eef2ff;
  color: #1e3a8a;
  font-size: 12px;
}

.editor-block {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #ffffff;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.editor-block-title {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.row-grid {
  display: grid;
  gap: 8px;
}

.row-char {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.5fr) auto;
}

.row-faction {
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) minmax(0, 1fr) auto;
}

.row-faction-rel {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) 120px auto;
}

.row-grid > * {
  min-width: 0;
}

.row-grid input,
.row-grid select {
  width: 100%;
  box-sizing: border-box;
  height: 34px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  padding: 0 10px;
  font-size: 12px;
  color: #0f172a;
  background: #fff;
}

.editor-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.add-btn,
.save-btn,
.danger-btn {
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #1e293b;
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
}

.save-btn {
  background: #0f172a;
  border-color: #0f172a;
  color: #fff;
}

.save-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.danger-btn {
  background: #fff1f2;
  border-color: #fecdd3;
  color: #be123c;
}

@media (max-width: 1440px) {
  .row-char,
  .row-faction,
  .row-faction-rel {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .row-grid .danger-btn {
    grid-column: 1 / -1;
    justify-self: end;
  }
}

@media (max-width: 1024px) {
  .row-char,
  .row-faction,
  .row-faction-rel {
    grid-template-columns: 1fr;
  }

  .row-grid .danger-btn {
    justify-self: start;
  }
}
</style>
