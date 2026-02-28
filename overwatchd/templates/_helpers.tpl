{{/*
Chart name, truncated to 63 characters.
Kubernetes names must be DNS-compliant: max 63 chars, lowercase alphanumeric + hyphens.
trimSuffix ensures we don't end with a hyphen after truncation.
*/}}
{{- define "overwatchd.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully qualified app name.
If the release name already contains the chart name (e.g. "overwatchd"), use it directly
to avoid stuttering ("overwatchd-overwatchd"). Otherwise, combine them.
This is the standard Helm convention — most resources use this as their metadata.name.
*/}}
{{- define "overwatchd.fullname" -}}
{{- if contains .Chart.Name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Common labels applied to every resource.
These follow the Kubernetes recommended label conventions:
  https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/

- helm.sh/chart: identifies which chart version created this resource (useful for debugging)
- app.kubernetes.io/version: the application version, for dashboards and kubectl queries
- app.kubernetes.io/managed-by: "Helm" — tells tools this resource is Helm-managed
- Selector labels are included so every resource carries them consistently.
*/}}
{{- define "overwatchd.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "overwatchd.selectorLabels" . }}
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels used in Deployment.spec.selector.matchLabels and Service.spec.selector.
These MUST be immutable after initial creation — Kubernetes forbids changing a Deployment's
selector. Keep them minimal: just app name + instance (release name).
Never put version or chart info here — those change on upgrades and would break selectors.
*/}}
{{- define "overwatchd.selectorLabels" -}}
app.kubernetes.io/name: {{ include "overwatchd.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name.
Allows overriding via values while defaulting to the release fullname.
*/}}
{{- define "overwatchd.serviceAccountName" -}}
{{- if .Values.serviceAccount.name }}
{{- .Values.serviceAccount.name }}
{{- else }}
{{- include "overwatchd.fullname" . }}
{{- end }}
{{- end }}

{{/*
Secret name.
When secrets.existingSecret is set, use that name (user manages the secret externally).
Otherwise, fall back to fullname — the convention is that the SealedSecret or
ExternalSecret creates a Secret with the same name as the release.
*/}}
{{- define "overwatchd.secretName" -}}
{{- if .Values.secrets.existingSecret }}
{{- .Values.secrets.existingSecret }}
{{- else }}
{{- include "overwatchd.fullname" . }}
{{- end }}
{{- end }}

{{/*
Full image reference: registry/repository:tag.
image.tag is required — there is no default. CI always sets it to a git SHA
or a release version. This ensures every deployment uses a pinned, immutable
image tag (never "latest" or "dev").
*/}}
{{- define "overwatchd.image" -}}
{{- if not .Values.image.tag }}
{{- fail "image.tag is required. Set it to a git SHA (e.g. 'a539516') or a release version (e.g. 'v1.0.0')." }}
{{- end }}
{{- printf "%s/%s:%s" .Values.image.registry .Values.image.repository .Values.image.tag }}
{{- end }}
