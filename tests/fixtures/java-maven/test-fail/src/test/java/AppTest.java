import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.fail;

public class AppTest {
    @Test
    void testIntentionallyFails() {
        fail("This test is designed to fail");
    }
}
