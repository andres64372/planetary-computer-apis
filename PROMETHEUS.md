# Horizonal Pod Autoscaler with Prometheus metrics

This project aims to demonstrate the implementation of Horizontal Pod Autoscaler (HPA) using Prometheus custom metrics for scaling a FastAPI service. Specifically, we will focus on extracting the number of HTTP requests per second from the FastAPI service as a metric for scaling.

## Prerequisites
- A running kubernetes cluster.
- kubectl.
- An existing app running.

## Installing Prometheus

1. Clone kube-prometheus repository available [here](https://github.com/prometheus-operator/kube-prometheus).
2. Identify in which namespaces are your services running. With `kubectl get ns` you can identify all existing namespaces and using `kubectl -n {your_namespace} get deployments`.
3. Once identified you should add them to prometheus roles in order to let the controller to scrape them, fot this locate following files:
    - Find `\manifests\prometheus-roleBindingSpecificNamespaces.yaml` and append a new RoleBinding

    ```yaml
    ...
    - apiVersion: rbac.authorization.k8s.io/v1
    kind: RoleBinding
    metadata:
        labels:
        app.kubernetes.io/component: prometheus
        app.kubernetes.io/instance: k8s
        app.kubernetes.io/name: prometheus
        app.kubernetes.io/part-of: kube-prometheus
        app.kubernetes.io/version: 2.44.0
        name: prometheus-k8s
        namespace: {your_namespace}
    roleRef:
        apiGroup: rbac.authorization.k8s.io
        kind: Role
        name: prometheus-k8s
    subjects:
    - kind: ServiceAccount
        name: prometheus-k8s
        namespace: monitoring
    ...
    kind: RoleBindingList
    ```
    - Find `\manifests\prometheus-roleSpecificNamespaces.yaml` and append a new Role
    ```yaml
    ...
    - apiVersion: rbac.authorization.k8s.io/v1
    kind: Role
    metadata:
        labels:
        app.kubernetes.io/component: prometheus
        app.kubernetes.io/instance: k8s
        app.kubernetes.io/name: prometheus
        app.kubernetes.io/part-of: kube-prometheus
        app.kubernetes.io/version: 2.44.0
        name: prometheus-k8s
        namespace: {your_namespace}
    rules:
    - apiGroups:
        - ""
        resources:
        - services
        - endpoints
        - pods
        verbs:
        - get
        - list
        - watch
    - apiGroups:
        - extensions
        resources:
        - ingresses
        verbs:
        - get
        - list
        - watch
    - apiGroups:
        - networking.k8s.io
        resources:
        - ingresses
        verbs:
        - get
        - list
        - watch
    ...
    kind: RoleList
    ```

Repeat this step for all namespaces that you want to add.

4. Install Prometheus CRD's and resources using following commands:

```
kubectl apply --server-side -f manifests/setup
kubectl apply -f manifests/
```

All these resources will be created on a namespace called monitoring including Alert Manager and Grafana.

## Instrument your application

Your application should expose and endpoint with metrics in prometheus format. Regarding to FastAPI there is an instrumentator available [here](https://pypi.org/project/prometheus-fastapi-instrumentator/).

Verify that your metrics are exposting accesing to `http://{your_service}/metrics`.

## Install custom metrics prometheus adapter

This adapter enables the scraping of metrics from Prometheus and exposes them through an API service, which can be utilized by the HPA. For this create a yaml with following content:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  labels:
    app: prometheus-adapter
  name: custom-metrics-prometheus-adapter
  namespace: monitoring
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  labels:
    app: prometheus-adapter
  name: prometheus-adapter-system-auth-delegator
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:auth-delegator
subjects:
- kind: ServiceAccount
  name: custom-metrics-prometheus-adapter
  namespace: monitoring
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  labels:
    app: prometheus-adapter
  name: prometheus-adapter-resource-reader
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: prometheus-adapter-resource-reader
subjects:
- kind: ServiceAccount
  name: custom-metrics-prometheus-adapter
  namespace: monitoring
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  labels:
    app: prometheus-adapter
  name: prometheus-adapter-resource-reader
rules:
- apiGroups:
  - ""
  resources:
  - namespaces
  - pods
  - services
  - configmaps
  verbs:
  - get
  - list
  - watch
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  labels:
    app: prometheus-adapter
  name: prometheus-adapter-auth-reader
  namespace: kube-system
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: extension-apiserver-authentication-reader
subjects:
- kind: ServiceAccount
  name: custom-metrics-prometheus-adapter
  namespace: monitoring
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: custom-metrics-prometheus-adapter
  namespace: monitoring
  labels:
    app: prometheus-adapter
data:
  config.yaml: |
    rules:
    - seriesQuery: 'http_requests_total{namespace!="",pod!=""}'
      resources:
        overrides:
          namespace:
            resource: namespace
          pod: 
            resource: pod
      name:
        matches: "^(.*)_total"
        as: "${1}_per_minute"
      metricsQuery: 'avg(rate(<<.Series>>{<<.LabelMatchers>>}[20s])) by (<<.GroupBy>>)'
    resourceRules:
      cpu:
        containerQuery: sum(rate(container_cpu_usage_seconds_total{<<.LabelMatchers>>, container_label_io_kubernetes_container_name!=""}[3m])) by (<<.GroupBy>>)
        nodeQuery: sum(rate(container_cpu_usage_seconds_total{<<.LabelMatchers>>, id='/'}[3m])) by (<<.GroupBy>>) by (<<.GroupBy>>)
        resources:
          overrides:
            container_label_io_kubernetes_pod_namespace:
              resource: namespace
            node:
              resource: node
            container_label_io_kubernetes_pod_name:
              resource: pod
        containerLabel: container_label_io_kubernetes_container_name
      memory:
        containerQuery: sum(container_memory_working_set_bytes{<<.LabelMatchers>>, container_label_io_kubernetes_container_name!=""}) by (<<.GroupBy>>)
        nodeQuery: sum(container_memory_working_set_bytes{<<.LabelMatchers>>,id='/'}) by (<<.GroupBy>>)
        resources:
          overrides:
            container_label_io_kubernetes_pod_namespace:
              resource: namespace
            node:
              resource: node
            container_label_io_kubernetes_pod_name:
              resource: pod
        containerLabel: container_label_io_kubernetes_container_name
      window: 3m
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: custom-metrics-prometheus-adapter
  namespace: monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prometheus-adapter
  template:
    metadata:
      labels:
        app: prometheus-adapter
      name: prometheus-adapter
      annotations:
        checksum/config: 4b70a56e35e56c8038b94f63f0515e79f22bd49456902c2f3c3d2dd9b2474ece
    spec:
      serviceAccountName: custom-metrics-prometheus-adapter
      containers:
      - name: prometheus-adapter
        image: "directxman12/k8s-prometheus-adapter-amd64:v0.8.4"
        imagePullPolicy: IfNotPresent
        args:
        - /adapter
        - --secure-port=6443
        - --cert-dir=/tmp/cert
        - --logtostderr=true
        - --prometheus-url=http://prometheus-operated.monitoring.svc:9090
        - --metrics-relist-interval=1m
        - --v=4
        - --config=/etc/adapter/config.yaml
        ports:
        - containerPort: 6443
          name: https
        livenessProbe:
          httpGet:
            path: /healthz
            port: https
            scheme: HTTPS
          initialDelaySeconds: 30
          timeoutSeconds: 5
        readinessProbe:
          httpGet:
            path: /healthz
            port: https
            scheme: HTTPS
          initialDelaySeconds: 30
          timeoutSeconds: 5
        resources:
          limits:
            cpu: 100m
            memory: 128Mi
          requests:
            cpu: 100m
            memory: 128Mi
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop: ["all"]
          readOnlyRootFilesystem: true
          runAsNonRoot: true
          runAsUser: 10001
        volumeMounts:
        - mountPath: /etc/adapter/
          name: config
          readOnly: true
        - mountPath: /tmp
          name: tmp
      volumes:
      - name: config
        configMap:
          name: custom-metrics-prometheus-adapter
      - name: tmp
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: custom-metrics-prometheus-adapter
  namespace: monitoring
  labels:
    app: prometheus-adapter
spec:
  ports:
  - port: 443
    protocol: TCP
    targetPort: https
  selector:
    app: prometheus-adapter
  type: ClusterIP
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  labels:
    app: prometheus-adapter
  name: prometheus-adapter-server-resources
rules:
- apiGroups:
  - custom.metrics.k8s.io
  resources: ["*"]
  verbs: ["*"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  labels:
    app: prometheus-adapter
  name: prometheus-adapter-hpa-controller
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: prometheus-adapter-server-resources
subjects:
- kind: ServiceAccount
  name: custom-metrics-prometheus-adapter
  namespace: monitoring
---
apiVersion: apiregistration.k8s.io/v1
kind: APIService
metadata:
  name: v1beta1.custom.metrics.k8s.io
  labels:
    app: prometheus-adapter
spec:
  service:
    name: custom-metrics-prometheus-adapter
    namespace: monitoring
  group: custom.metrics.k8s.io
  version: v1beta1
  insecureSkipTLSVerify: true
  groupPriorityMinimum: 100
  versionPriority: 100
```

After that run `kubectl apply -f custom-metrics.yaml`

Note that in following section you can 

```yaml
...
data:
  config.yaml: |
    rules:
    - seriesQuery: 'http_requests_total{namespace!="",pod!=""}'
      resources:
        overrides:
          namespace:
            resource: namespace
          pod: 
            resource: pod
      name:
        matches: "^(.*)_total"
        as: "${1}_per_minute"
      metricsQuery: 'avg(rate(<<.Series>>{<<.LabelMatchers>>}[20s])) by (<<.GroupBy>>)'
    resourceRules:
...
```