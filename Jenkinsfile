def section = { String title ->
  echo """
========================================
  ${title}
========================================
"""
}

def prepareImageName(imageRep, deployEnv) {
  def buildTag  = sh(script: 'git rev-parse --short=8 HEAD', returnStdout: true).trim()
  def imageName = "${imageRep}:${deployEnv}-${buildTag}".toLowerCase()
  echo "IMAGE_NAME = ${imageName}"
  return [buildTag: buildTag, imageName: imageName]
}

pipeline {
  agent { label 'devops-agent' }

  parameters {
    choice(
      name: 'DEPLOY_SERVICE',
      choices: ['mcp-server', 'skills-store', 'emarsys-sync'],
      description: '选择要构建和部署的服务（DEPLOY_ENV / BRANCH_NAME 由上游传入）'
    )
  }

  environment {
    GIT_REPO_SSH     = "https://tfs2015.techsun.com/tfs/DefaultCollection"
    GIT_PROJECT      = "Socialhub-CLI"
    GIT_REPO_NAME    = "Socialhub-CLI"
    SERVICE_CODEPATH = "${WORKSPACE}"
    HARBOR_HOST      = "harbor.easesaas.com"
    IMAGE_DIR        = "marpro"
    KUBE_CONFIG_ID   = "socialhub-k8s-azurencus"
    KUBE_NAMESPACE   = "socialhub-cli"
  }

  stages {

    stage("code clone") {
      steps {
        script { section("code clone") }

        git branch: "${env.BRANCH_NAME}",
            credentialsId: "TECHSUN-TFS-JENKINS",
            url: "${env.GIT_REPO_SSH}/${env.GIT_PROJECT}/_git/${env.GIT_REPO_NAME}"

        script {
          if (env.TAG_NAME?.trim()) {
            sh "git checkout ${env.TAG_NAME}"
          }

          // 服务配置映射：镜像名 / deployment 文件路径 / Dockerfile 路径
          def serviceConfig = [
            'mcp-server'  : [
              image     : 'socialhub-mcp-server',
              deployFile: 'k8s/base/mcp-server-deployment.yaml',
              dockerfile: 'docker/mcp-server.Dockerfile'
            ],
            'skills-store': [
              image     : 'socialhub-skills-store',
              deployFile: 'k8s/base/skills-store-deployment.yaml',
              dockerfile: 'docker/skills-store.Dockerfile'
            ],
            'emarsys-sync': [
              image     : 'socialhub-emarsys-sync',
              deployFile: 'k8s/base/emarsys-sync-deployment.yaml',
              dockerfile: 'docker/emarsys-sync.Dockerfile'
            ]
          ]

          def svc = serviceConfig[params.DEPLOY_SERVICE]
          if (!svc) { error("未知服务: ${params.DEPLOY_SERVICE}") }

          env.SVC_IMAGE_NAME  = svc.image
          env.SVC_DEPLOY_FILE = svc.deployFile
          env.SVC_DOCKERFILE  = svc.dockerfile
          env.DEPLOY_NAME     = "socialhub-${params.DEPLOY_SERVICE}"

          def r          = prepareImageName("${env.HARBOR_HOST}/${env.IMAGE_DIR}/${env.SVC_IMAGE_NAME}", env.DEPLOY_ENV)
          env.BUILD_TAG  = r.buildTag
          env.IMAGE_NAME = r.imageName
        }
      }
    }

    stage("image build") {
      steps {
        container('dind') {
          script { section("docker 镜像构建") }
          sh 'until docker info > /dev/null 2>&1; do echo "Waiting for docker daemon..."; sleep 2; done'
          sh "docker build -t ${env.IMAGE_NAME} -f ${env.SERVICE_CODEPATH}/${env.SVC_DOCKERFILE} ${env.SERVICE_CODEPATH}"
        }
      }
    }

    stage("image push") {
      steps {
        container('dind') {
          script { section("docker 镜像推送") }
          withCredentials([usernamePassword(credentialsId: 'TECHSUN-HARBOR-JENKINS', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASSWORD')]) {
            sh "echo ${DOCKER_PASSWORD} | docker login ${env.HARBOR_HOST} -u ${DOCKER_USER} --password-stdin"
            sh "docker push ${env.IMAGE_NAME}"
            sh "docker rmi ${env.IMAGE_NAME}"
          }
        }
      }
    }

    stage("service deploy") {
      steps {
        container('kubectl') {
          script { section("服务部署") }
          configFileProvider([
            configFile(fileId: env.KUBE_CONFIG_ID, targetLocation: "${WORKSPACE}/KUBECONFIG")
          ]) {
            sh """
              sed -i 's#${env.HARBOR_HOST}/${env.IMAGE_DIR}/${env.SVC_IMAGE_NAME}:.*#${env.IMAGE_NAME}#' \
                  ${env.SERVICE_CODEPATH}/${env.SVC_DEPLOY_FILE}
              echo "deployment yaml file start=========================="
              cat ${env.SERVICE_CODEPATH}/${env.SVC_DEPLOY_FILE}
              echo "deployment yaml file end============================"

              kubectl --kubeconfig=${WORKSPACE}/KUBECONFIG \
                  create namespace ${env.KUBE_NAMESPACE} \
                  --dry-run=client -o yaml | \
              kubectl --kubeconfig=${WORKSPACE}/KUBECONFIG apply -f -

              kubectl --kubeconfig=${WORKSPACE}/KUBECONFIG \
                  -n ${env.KUBE_NAMESPACE} apply -f ${env.SERVICE_CODEPATH}/${env.SVC_DEPLOY_FILE}

              kubectl --kubeconfig=${WORKSPACE}/KUBECONFIG \
                  -n ${env.KUBE_NAMESPACE} rollout status deployment/${env.DEPLOY_NAME} \
                  --timeout=120s
            """
          }
        }
      }
    }

  }
}