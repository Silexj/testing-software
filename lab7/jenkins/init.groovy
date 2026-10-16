import jenkins.model.Jenkins
import hudson.security.HudsonPrivateSecurityRealm
import hudson.security.FullControlOnceLoggedInAuthorizationStrategy
import hudson.plugins.git.GitSCM
import hudson.plugins.git.UserRemoteConfig
import hudson.plugins.git.BranchSpec
import org.jenkinsci.plugins.workflow.job.WorkflowJob
import org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition
import com.cloudbees.plugins.credentials.SystemCredentialsProvider
import com.cloudbees.plugins.credentials.CredentialsScope
import org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl
import hudson.util.Secret

// Only bootstrap this dedicated local training instance, never an existing Jenkins.
def j = Jenkins.get()
def marker = new File(j.rootDir, 'lab7-bootstrap-complete')
if (!marker.exists()) {
    def adminPassword = new File('/run/secrets/jenkins-admin-password').text.trim()
    def bmcPassword = new File('/run/secrets/bmc-password').text.trim()
    assert adminPassword.size() >= 16
    assert bmcPassword
    def realm = new HudsonPrivateSecurityRealm(false)
    realm.createAccount('labadmin', adminPassword)
    j.setSecurityRealm(realm)
    def auth = new FullControlOnceLoggedInAuthorizationStrategy()
    auth.setAllowAnonymousRead(false)
    j.setAuthorizationStrategy(auth)
    j.setNumExecutors(1)
    def store = SystemCredentialsProvider.getInstance()
    store.credentials.add(new StringCredentialsImpl(CredentialsScope.GLOBAL,
        'openbmc-password', 'Password of the disposable lab firmware', Secret.fromString(bmcPassword)))
    store.save()
    def job = j.createProject(WorkflowJob, 'openbmc-lab7')
    def scm = new GitSCM(
        [new UserRemoteConfig('https://github.com/Silexj/testing-software.git', null, null, null)],
        [new BranchSpec('*/lab7-jenkins-ci')], false, [], null, null, [])
    def definition = new CpsScmFlowDefinition(scm, 'Jenkinsfile')
    definition.setLightweight(true)
    job.setDefinition(definition)
    job.save()
    j.save()
    marker.text = 'Configured local lab Jenkins with authentication and GitHub SCM\n'
}
